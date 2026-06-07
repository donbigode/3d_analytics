"""Dialect identifiers for gcode sources.

Today the parser auto-detects Creality K-series headers. This module
exists so future slicers (Bambu, PrusaSlicer, OrcaSlicer) can register
specific extraction overrides without touching the parser's hot path.
"""

from enum import Enum


class Dialect(str, Enum):
    CREALITY = "creality"
    BAMBU = "bambu"
    PRUSA = "prusa"
    ORCA = "orca"
    UNKNOWN = "unknown"
