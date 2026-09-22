import io
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from backend.settings import get_settings

logger = logging.getLogger(__name__)

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


def copy_photo_file(src_rel: str | None) -> SavedPhoto | None:
    """Copia uma foto já armazenada para um arquivo novo.

    Usado pelo clone. Compartilhar o storage_path faria delete_photo() no
    original apagar a imagem do clone — quote_photos é diretório plano,
    sem pasta por orçamento.

    Devolve None em duas condições, e nas duas o clone segue sem essa foto
    em vez de falhar (o pulo fica registrado em log com o storage_path e o
    motivo):
    - a origem não existe em disco (mesma regra do clone de gcode);
    - a origem existe mas está corrompida (ex.: JPEG truncado por disco
      cheio) e o reencode do save_photo falha com ValueError. Só esse
      ValueError é engolido — um erro na ESCRITA da cópia (disco cheio
      *agora*, por exemplo) é outra coisa e continua subindo.
    """
    if not src_rel:
        return None
    settings = get_settings()
    src = Path(settings.storage_dir) / src_rel
    if not src.is_file():
        logger.warning("clone: foto pulada, arquivo ausente em disco: %s", src_rel)
        return None
    try:
        # Reusa save_photo para manter o mesmo reencode e os mesmos metadados.
        return save_photo(src.read_bytes(), src.name)
    except ValueError as exc:
        logger.warning("clone: foto pulada, arquivo corrompido: %s (%s)", src_rel, exc)
        return None


def delete_photo(storage_path: str | None) -> None:
    if not storage_path:
        return
    p = Path(get_settings().storage_dir) / storage_path
    if p.exists():
        p.unlink()


def absolute_uri(storage_path: str) -> str:
    return (Path(get_settings().storage_dir) / storage_path).as_uri()
