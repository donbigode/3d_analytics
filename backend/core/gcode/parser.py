"""Best-effort gcode header parser.

Gcode is plain text and every slicer writes its own dialect, so we don't
demand a specific format. Strategy:

1. Read the first ~800 comment lines (everything before real G-commands).
2. For each line, try a battery of patterns to extract time, filament
   length, material and printer name. First match wins per field.
3. Never raise. If nothing was found, return zeros — the upload still
   succeeds and the user can fill in the gaps manually.

Recognised dialects today (and counting):

* **Cura / Creality Print (Cura-derived)** — ``;TIME:14400``,
  ``;Filament used: 4.567 m``, ``;Material Type: PLA``, ``;Machine Name:``
* **PrusaSlicer / Bambu Studio / OrcaSlicer / Creality Print 5+** —
  ``; total estimated time: 5h 32m 14s``, ``; estimated printing time
  (normal mode) = 1h 12m 3s``, ``; total filament used [mm] = ...``,
  ``; filament_type = PLA``, ``; printer_model = ...``
* **Generic fuzzy fallback** — any comment line with the words
  ``time``/``duration`` + a duration token (``HH:MM:SS``, ``2h 35m``,
  ``14400``), and ``filament`` + a length token in mm/m.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# --- Cura / Creality Print -------------------------------------------------
RE_TIME = re.compile(r";\s*TIME\s*:\s*([\d.]+)", re.IGNORECASE)
RE_FILAMENT = re.compile(r";\s*Filament used\s*:\s*([\d.]+)\s*m\b", re.IGNORECASE)
RE_MATERIAL = re.compile(r";\s*Material Type\s*:\s*([^\s;]+)", re.IGNORECASE)
RE_MACHINE = re.compile(r";\s*Machine Name\s*:\s*(.+)", re.IGNORECASE)

# --- PrusaSlicer / Bambu Studio / OrcaSlicer -------------------------------
RE_TIME_HUMAN = re.compile(
    r";\s*(?:total\s+)?estimated(?:\s+printing)?\s+time"
    r"(?:\s*\([^)]+\))?\s*[:=]\s*"
    r"((?:\d+\s*[hms]\s*)+)",
    re.IGNORECASE,
)
RE_FILAMENT_MM = re.compile(
    r";\s*(?:total\s+)?filament used\s*\[mm\]\s*[=:]\s*([\d.]+)", re.IGNORECASE
)
RE_FILAMENT_M_BARE = re.compile(
    r";\s*(?:total\s+)?filament used\s*\[m\]\s*[=:]\s*([\d.]+)", re.IGNORECASE
)
RE_FILAMENT_TYPE = re.compile(
    r";\s*filament_type\s*[:=]\s*([A-Za-z][A-Za-z0-9_+\-]*)", re.IGNORECASE
)
RE_PRINTER_MODEL = re.compile(r";\s*printer_model\s*[:=]\s*(.+)", re.IGNORECASE)

# --- Generic fuzzy fallback ------------------------------------------------
# Used when no dialect-specific regex matched. Each pattern is intentionally
# loose; the caller cross-checks the keyword (``time``/``filament``) so we
# don't accidentally grab numbers from unrelated comments.
RE_FUZZY_HMS_COLON = re.compile(r"\b(\d{1,3}):(\d{2}):(\d{2})\b")
RE_FUZZY_HUMAN_TIME = re.compile(
    r"((?:\d+(?:\.\d+)?\s*[hms]\b\s*){1,3})", re.IGNORECASE
)
RE_FUZZY_BARE_SECONDS = re.compile(r"(?:[=:]|\bis\b|\babout\b)\s*([\d.]+)\s*(?:s|sec|seconds)?\b", re.IGNORECASE)
RE_FUZZY_MM = re.compile(r"([\d.]+)\s*mm\b", re.IGNORECASE)
RE_FUZZY_METERS = re.compile(r"([\d.]+)\s*(?:m|meters?)\b", re.IGNORECASE)
RE_FUZZY_MATERIAL_TOKEN = re.compile(
    r"\b(PLA(?:[-+ ]?(?:PRO|PLUS|HF|HS|CF|GF))?|PETG(?:[-+ ]?CF)?|ABS|ASA|TPU|"
    r"PC|PA|NYLON|HIPS|PVA|PEEK|PEI|WOOD|HYPER[-_ ]?PLA|SILK[-_ ]?PLA)\b",
    re.IGNORECASE,
)

_TIME_KEYWORDS = ("time", "duration", "duração", "duracao", "tempo")
# NB: "extrusion" foi removido — casava com linhas de config "extrusion width
# = 0.42mm" e gerava consumo espúrio. O consumo real ("filament used [mm]")
# é coberto pelos regex de dialeto; a fuzzy fica restrita a "filament".
_FILAMENT_KEYWORDS = ("filament", "filamento")
_MATERIAL_KEYWORDS = ("material", "filament_type", "filament type")
_MACHINE_KEYWORDS = ("printer", "machine", "model", "impressora")


@dataclass(frozen=True)
class GcodeMeta:
    time_s: float
    filament_m: float
    material: str | None
    machine: str | None


def _humantime_to_seconds(token: str) -> float | None:
    """``"5h 32m 14s"`` → ``19934.0``. Missing units are tolerated."""
    total = 0.0
    matched = False
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([hms])", token, re.I):
        v = float(value)
        if unit.lower() == "h":
            total += v * 3600
        elif unit.lower() == "m":
            total += v * 60
        else:
            total += v
        matched = True
    return total if matched else None


def _fuzzy_extract_time(line: str) -> float | None:
    """Look for a duration anywhere on a comment line that mentions time."""
    if not any(kw in line.lower() for kw in _TIME_KEYWORDS):
        return None
    m = RE_FUZZY_HMS_COLON.search(line)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = RE_FUZZY_HUMAN_TIME.search(line)
    if m:
        t = _humantime_to_seconds(m.group(1))
        if t and t > 0:
            return t
    # Bare seconds (e.g. ``;time = 14400`` or ``;Print Time: 14400``).
    # Only believe values above a minute to dodge layer/index counters.
    m = RE_FUZZY_BARE_SECONDS.search(line)
    if m:
        try:
            v = float(m.group(1))
            if v >= 60:
                return v
        except ValueError:
            pass
    return None


def _fuzzy_extract_filament(line: str) -> float | None:
    """Length in metres if the line mentions filament + a unit."""
    if not any(kw in line.lower() for kw in _FILAMENT_KEYWORDS):
        return None
    m = RE_FUZZY_MM.search(line)
    if m:
        try:
            return float(m.group(1)) / 1000.0
        except ValueError:
            pass
    m = RE_FUZZY_METERS.search(line)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _fuzzy_extract_material(line: str) -> str | None:
    if not any(kw in line.lower() for kw in _MATERIAL_KEYWORDS):
        return None
    m = RE_FUZZY_MATERIAL_TOKEN.search(line)
    if m:
        return m.group(1).strip().upper().replace(" ", "-")
    return None


def _fuzzy_extract_machine(line: str) -> str | None:
    if not any(kw in line.lower() for kw in _MACHINE_KEYWORDS):
        return None
    # Grab "key = value" / "key: value" — the value side after the separator.
    m = re.search(r"[:=]\s*(.+)$", line)
    if m:
        val = m.group(1).strip().strip(",;")
        # Reject if it looks like a duration or number-only.
        if val and not val.replace(".", "").replace(" ", "").isdigit():
            return val[:120]
    return None


def _scan_line(line, t, f, mat, mach):
    """Apply the pattern battery to one comment line; only fills fields still
    None so the first match per field wins. Returns the updated tuple."""
    # Dialect-specific fast path
    if t is None and (m := RE_TIME.search(line)):
        t = float(m.group(1))
    elif t is None and (m := RE_TIME_HUMAN.search(line)):
        t = _humantime_to_seconds(m.group(1))
    if f is None and (m := RE_FILAMENT.search(line)):
        f = float(m.group(1))
    elif f is None and (m := RE_FILAMENT_MM.search(line)):
        f = float(m.group(1)) / 1000.0
    elif f is None and (m := RE_FILAMENT_M_BARE.search(line)):
        f = float(m.group(1))
    if mat is None and (m := RE_MATERIAL.search(line)):
        mat = m.group(1).strip().upper()
    elif mat is None and (m := RE_FILAMENT_TYPE.search(line)):
        mat = m.group(1).strip().split(";")[0].upper()
    if mach is None and (m := RE_MACHINE.search(line)):
        mach = m.group(1).strip()
    elif mach is None and (m := RE_PRINTER_MODEL.search(line)):
        mach = m.group(1).strip()
    # Generic fuzzy fallback — only if the specific patterns failed.
    if t is None:
        t = _fuzzy_extract_time(line)
    if f is None:
        f = _fuzzy_extract_filament(line)
    if mat is None:
        mat = _fuzzy_extract_material(line)
    if mach is None:
        mach = _fuzzy_extract_machine(line)
    return t, f, mat, mach


def _tail_comment_lines(path: Path, tail_bytes: int) -> list[str]:
    """Comment lines from the last ``tail_bytes`` of the file. Creality Print
    V7 / PrusaSlicer / Cura write the filament & time totals in a FOOTER, far
    past the header — so we read the end of the file too."""
    try:
        size = path.stat().st_size
    except OSError:
        return []
    with open(path, "rb") as fh:
        if size > tail_bytes:
            fh.seek(size - tail_bytes)
            fh.readline()  # discard the partial first line after the seek
        chunk = fh.read()
    text = chunk.decode("utf-8", errors="ignore")
    return [ln for ln in text.splitlines() if ln.startswith(";")]


def parse_gcode_metadata(
    path: Path, max_lines: int = 800, tail_bytes: int = 131072
) -> GcodeMeta:
    t: float | None = None
    f: float | None = None
    mat: str | None = None
    mach: str | None = None

    # 1) Head: material/machine and header-style stats live near the top.
    with open(path, "r", errors="ignore") as fh:
        for i, line in enumerate(fh):
            if i > max_lines:
                break
            if not line.startswith(";"):
                continue  # actual gcode commands; skip
            t, f, mat, mach = _scan_line(line, t, f, mat, mach)

    # 2) Footer: if time/filament/material are still missing, scan the tail.
    if t is None or f is None or mat is None:
        for line in _tail_comment_lines(path, tail_bytes):
            t, f, mat, mach = _scan_line(line, t, f, mat, mach)
            if t is not None and f is not None and mat is not None:
                break

    return GcodeMeta(time_s=t or 0.0, filament_m=f or 0.0, material=mat, machine=mach)
