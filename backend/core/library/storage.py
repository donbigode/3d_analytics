"""Content-addressed storage for library assets.

Files land at ``<STORAGE_DIR>/library/<format>/<sha256>.<ext>``. We pick the
hash as the filename so the path is stable and we never have to disambiguate
two assets that happen to share an upload filename.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from backend.settings import get_settings


class LibrarySaveError(Exception):
    """Raised when we can't persist an upload (disk full, IO error, etc)."""


def compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def storage_path_for(file_hash: str, fmt: str) -> Path:
    base = Path(get_settings().storage_dir) / "library" / fmt
    return base / f"{file_hash}.{fmt}"


def save_bytes(content: bytes, *, fmt: str, file_hash: str | None = None) -> tuple[Path, str]:
    """Persist bytes to the library and return ``(path, hash)``.

    Returns the same path when called twice with the same content — the dedup
    is the caller's responsibility (the DB has a UNIQUE on file_hash).
    """
    digest = file_hash or compute_hash(content)
    dest = storage_path_for(digest, fmt)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(content)
    except OSError as exc:
        raise LibrarySaveError(str(exc)) from exc
    return dest, digest
