"""Format detection + best-effort metadata extraction.

Two families of assets live in the library:

* **Printable** — the actual jobs sent to the printer (gcode/3mf/stl …).
  For these we try to extract slicer metadata (time, filament, material)
  so quotes and analytics can reuse them without re-slicing.
* **Auxiliary** — supplementary docs the user wants to keep alongside a
  project: PDFs, READMEs, photos, spec sheets, spreadsheets. We accept
  them verbatim, parsed_meta stays empty.

Format detection takes the last filename extension (case-insensitive).
That naturally handles double-extensions like ``model.gcode.3mf`` (which
Bambu/Orca emit) — the file is really a 3MF wrapper, so detecting it as
``3mf`` is correct.
"""
from __future__ import annotations

import io
import logging
import re
import tempfile
import zipfile
from pathlib import Path

from backend.core.gcode.parser import parse_gcode_metadata

logger = logging.getLogger(__name__)

# Printable assets — what actually gets sliced and printed. The order
# matters for prioritisation in pick_best_file() consumers but not for
# detection itself.
PRINTABLE_FORMATS = ("gcode", "bgcode", "gco", "g", "3mf", "stl", "obj", "step", "stp")

# Auxiliary docs — accepted as complementary info, not parsed.
AUXILIARY_FORMATS = (
    "pdf", "doc", "docx", "txt", "md", "rtf",
    "png", "jpg", "jpeg", "webp", "gif",
    "csv", "xlsx", "xls",
    "zip",
)

SUPPORTED_FORMATS = PRINTABLE_FORMATS + AUXILIARY_FORMATS

# Common Slic3r/Prusa/Orca metadata lines inside a 3MF's config files.
_3MF_TIME_RX = re.compile(r"estimated printing time(?:[^=]*?)\s*=\s*([\d:hms ]+)", re.I)
_3MF_FILAMENT_M_RX = re.compile(r"total filament used\s*=\s*([\d.]+)\s*mm", re.I)
_3MF_FILAMENT_G_RX = re.compile(r"total filament used\s*=\s*([\d.]+)\s*g", re.I)
_3MF_PRINT_TIME_LINE = re.compile(
    r"(?:total estimated time|estimated_print_time)\s*[=:]\s*([\d.]+)\s*(s|sec|seconds)?",
    re.I,
)


def detect_format(filename: str) -> str | None:
    """Return one of SUPPORTED_FORMATS or ``None`` for unsupported files.

    Picks the last extension after the final dot — handles ``foo.gcode.3mf``
    (returns ``3mf``) and tolerates uppercase (``Model.STL`` → ``stl``).
    """
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[-1].lower()
    return ext if ext in SUPPORTED_FORMATS else None


def is_printable(fmt: str) -> bool:
    return fmt in PRINTABLE_FORMATS


def _parse_duration_to_seconds(token: str) -> float | None:
    """Convert '4h 23m 12s' or '263 s' or '15842' into seconds."""
    token = token.strip()
    if not token:
        return None
    # Pure number → seconds
    try:
        return float(token)
    except ValueError:
        pass
    # 1h 2m 3s style
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
    if not matched:
        return None
    return total


def _parse_3mf(content: bytes) -> dict:
    """Best-effort extraction from a Prusa/Orca 3MF."""
    meta: dict = {}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist():
                if not name.endswith((".config", ".gcode", "config.txt", ".ini")):
                    continue
                try:
                    body = zf.read(name).decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if "time_s" not in meta:
                    m = _3MF_TIME_RX.search(body)
                    if m:
                        secs = _parse_duration_to_seconds(m.group(1))
                        if secs:
                            meta["time_s"] = secs
                if "time_s" not in meta:
                    m = _3MF_PRINT_TIME_LINE.search(body)
                    if m:
                        secs = _parse_duration_to_seconds(m.group(1))
                        if secs:
                            meta["time_s"] = secs
                if "filament_m" not in meta:
                    m = _3MF_FILAMENT_M_RX.search(body)
                    if m:
                        try:
                            meta["filament_m"] = float(m.group(1)) / 1000.0  # mm → m
                        except ValueError:
                            pass
                if "filament_g" not in meta:
                    m = _3MF_FILAMENT_G_RX.search(body)
                    if m:
                        try:
                            meta["filament_g"] = float(m.group(1))
                        except ValueError:
                            pass
                # Material guess: look for "filament_type" inside config
                if "material" not in meta:
                    fm = re.search(r"filament_type\s*=\s*([A-Z][A-Z0-9-]+)", body, re.I)
                    if fm:
                        meta["material"] = fm.group(1).strip().upper()
    except zipfile.BadZipFile:
        logger.info("3mf parse: not a valid zip")
    except Exception as exc:  # noqa: BLE001
        logger.info("3mf parse error: %s", exc)
    return meta


def parse_meta_for_format(content: bytes, fmt: str) -> dict:
    """Return a best-effort ``{time_s, filament_m, material, machine}`` dict.

    Always returns a dict — possibly empty — never raises. Auxiliary
    formats (pdf/png/docx/…) skip parsing entirely.
    """
    if fmt in ("gcode", "bgcode", "gco", "g"):
        try:
            with tempfile.NamedTemporaryFile(suffix="." + fmt, delete=True) as tf:
                tf.write(content)
                tf.flush()
                gm = parse_gcode_metadata(Path(tf.name))
            return {
                "time_s": gm.time_s,
                "filament_m": gm.filament_m,
                "material": gm.material,
                "machine": gm.machine,
            }
        except Exception as exc:  # noqa: BLE001
            logger.info("gcode parse error: %s", exc)
            return {}
    if fmt == "3mf":
        return _parse_3mf(content)
    # stl/obj/step/stp → geometry only; auxiliary formats → not parsed.
    return {}
