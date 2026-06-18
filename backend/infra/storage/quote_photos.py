import io
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from backend.settings import get_settings

MAX_DIM = 1600
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}


@dataclass
class SavedPhoto:
    storage_path: str
    content_type: str
    size_bytes: int
    width: int
    height: int


def save_photo(content: bytes, filename: str) -> SavedPhoto:
    """Valida, corrige orientação EXIF, redimensiona pra MAX_DIM e reencoda JPEG."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        raise ValueError("tipo de arquivo não suportado")
    try:
        img = Image.open(io.BytesIO(content))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as exc:
        raise ValueError("imagem inválida") from exc
    img.thumbnail((MAX_DIM, MAX_DIM))  # só reduz, mantém proporção

    settings = get_settings()
    photos_dir = Path(settings.storage_dir) / "quote_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    dest = photos_dir / f"{uuid4().hex}.jpg"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    data = buf.getvalue()
    dest.write_bytes(data)
    return SavedPhoto(
        storage_path=str(dest.relative_to(settings.storage_dir)),
        content_type="image/jpeg",
        size_bytes=len(data),
        width=img.width,
        height=img.height,
    )


def delete_photo(storage_path: str | None) -> None:
    if not storage_path:
        return
    p = Path(get_settings().storage_dir) / storage_path
    if p.exists():
        p.unlink()


def absolute_uri(storage_path: str) -> str:
    return (Path(get_settings().storage_dir) / storage_path).as_uri()
