import re
from dataclasses import dataclass
from pathlib import Path

RE_TIME = re.compile(r";\s*TIME\s*:\s*([\d.]+)", re.IGNORECASE)
RE_FILAMENT = re.compile(r";\s*Filament used\s*:\s*([\d.]+)\s*m", re.IGNORECASE)
RE_MATERIAL = re.compile(r";\s*Material Type\s*:\s*([^\s;]+)", re.IGNORECASE)
RE_MACHINE = re.compile(r";\s*Machine Name\s*:\s*(.+)", re.IGNORECASE)


@dataclass(frozen=True)
class GcodeMeta:
    time_s: float
    filament_m: float
    material: str | None
    machine: str | None


def parse_gcode_metadata(path: Path, max_lines: int = 400) -> GcodeMeta:
    t = f = None
    mat = mach = None
    with open(path, "r", errors="ignore") as fh:
        for i, line in enumerate(fh):
            if i > max_lines:
                break
            if t is None and (m := RE_TIME.search(line)):
                t = float(m.group(1))
            if f is None and (m := RE_FILAMENT.search(line)):
                f = float(m.group(1))
            if mat is None and (m := RE_MATERIAL.search(line)):
                mat = m.group(1).strip().upper()
            if mach is None and (m := RE_MACHINE.search(line)):
                mach = m.group(1).strip()
    if t is None and f is None:
        raise ValueError(f"Not a recognized gcode: {path}")
    return GcodeMeta(time_s=t or 0.0, filament_m=f or 0.0, material=mat, machine=mach)
