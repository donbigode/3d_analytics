"""Library module — local-first store for 3D-printing files.

Public surface:
  - save_bytes() / save_upload(): persist a file, dedup by SHA-256
  - parse_meta_for_format(): try to extract time/filament from a file
  - SUPPORTED_FORMATS: enum-like
"""
from backend.core.library.parsers import (
    AUXILIARY_FORMATS,
    PRINTABLE_FORMATS,
    SUPPORTED_FORMATS,
    detect_format,
    is_printable,
    parse_meta_for_format,
)
from backend.core.library.storage import (
    LibrarySaveError,
    compute_hash,
    save_bytes,
    storage_path_for,
)

__all__ = [
    "AUXILIARY_FORMATS",
    "PRINTABLE_FORMATS",
    "SUPPORTED_FORMATS",
    "LibrarySaveError",
    "compute_hash",
    "detect_format",
    "is_printable",
    "parse_meta_for_format",
    "save_bytes",
    "storage_path_for",
]
