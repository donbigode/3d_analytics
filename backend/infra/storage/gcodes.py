from pathlib import Path
from uuid import UUID

from backend.settings import get_settings


def save_gcode(quote_id: UUID, filename: str, content: bytes) -> str:
    """Persist gcode bytes under <STORAGE_DIR>/gcodes/<quote_id>/<filename>.

    Returns the path relative to STORAGE_DIR so callers can persist a portable reference.
    """
    storage_dir = Path(get_settings().storage_dir)
    base = storage_dir / "gcodes" / str(quote_id)
    base.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name or "upload.gcode"
    dest = base / safe_name
    dest.write_bytes(content)
    return str(dest.relative_to(storage_dir))
