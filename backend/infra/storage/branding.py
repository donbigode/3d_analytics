from pathlib import Path
from backend.settings import get_settings


def save_logo(filename: str, content: bytes) -> str:
    settings = get_settings()
    branding_dir = Path(settings.storage_dir) / "branding"
    branding_dir.mkdir(parents=True, exist_ok=True)
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in {"png", "jpg", "jpeg", "svg"}:
        raise ValueError("unsupported file type")
    dest = branding_dir / f"logo.{ext}"
    dest.write_bytes(content)
    return str(dest.relative_to(settings.storage_dir))


def delete_logo(current_path: str | None) -> None:
    if not current_path:
        return
    settings = get_settings()
    p = Path(settings.storage_dir) / current_path
    if p.exists():
        p.unlink()
