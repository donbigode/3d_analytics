import shutil
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


def copy_gcode(src_rel: str | None, dest_quote_id: UUID) -> str | None:
    """Copia um gcode já armazenado para a pasta de outro orçamento.

    Usado pelo clone: compartilhar o caminho faria o item do clone apontar
    para a pasta do original, e o reparse quebraria assim que o original
    fosse limpo.

    Devolve o caminho relativo novo, ou None quando a origem não existe em
    disco (histórico anterior ao armazenamento) — nesse caso o clone segue
    com o item sem arquivo.
    """
    if not src_rel:
        return None
    storage_dir = Path(get_settings().storage_dir)
    src = storage_dir / src_rel
    if not src.is_file():
        return None
    base = storage_dir / "gcodes" / str(dest_quote_id)
    base.mkdir(parents=True, exist_ok=True)
    dest = base / src.name
    shutil.copy2(src, dest)
    return str(dest.relative_to(storage_dir))
