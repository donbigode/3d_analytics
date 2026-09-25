"""Itens de orçamento: adicionar, atualizar, reanalisar gcode, remover.

Movido sem alteração de lógica a partir do antigo `backend/api/routes/quotes.py`.
"""
import logging
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.quotes import QuoteItemUpdate, QuoteOut
from backend.api.routes.quotes._shared import _quote_out
from backend.core.gcode.parser import GcodeMeta, parse_gcode_metadata
from backend.core.models import QuoteStatus
from backend.infra.db.models import Quote, QuoteItem, QuotePhoto, User
from backend.infra.db.repos import material as material_repo
from backend.infra.storage import quote_photos as photo_storage
from backend.infra.storage.gcodes import save_gcode
from backend.settings import get_settings as get_app_settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------- Items ----------

@router.post("/{quote_id}/items", response_model=QuoteOut, status_code=201)
async def add_item(
    quote_id: UUID,
    name: str = Form(...),
    file: UploadFile | None = File(None),
    quantity: int = Form(1),
    model_source_url: str | None = Form(None),
    model_source_author: str | None = Form(None),
    model_source_license: str | None = Form(None),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")

    rel_path: str | None = None
    meta = GcodeMeta(time_s=0.0, filament_m=0.0, material=None, machine=None)
    if file is not None and file.filename:
        content = await file.read()
        if content:
            # Parse is best-effort: when the slicer dialect isn't recognised we
            # still accept the file and let the user fill in time/filament
            # manually via the inline editor. Rejecting outright would leave
            # them stuck with no path to enter the data.
            try:
                with tempfile.NamedTemporaryFile(suffix=".gcode", delete=True) as tf:
                    tf.write(content)
                    tf.flush()
                    meta = parse_gcode_metadata(Path(tf.name))
            except ValueError as exc:
                logger.info("gcode parse fallback for quote %s: %s", quote_id, exc)
            rel_path = save_gcode(q.id, file.filename or "upload.gcode", content)

    material_type = meta.material or "PLA"
    # Auto-resolve only when exactly one current material matches the polymer
    # type. With multiple manufacturers/colors registered, leave the item
    # pending so the user picks one explicitly.
    mv = await material_repo.auto_resolve_for_gcode(session, material_type)

    item = QuoteItem(
        quote_id=q.id,
        name=name,
        filename=rel_path,
        gcode_meta={
            "time_s": meta.time_s,
            "filament_m": meta.filament_m,
            "material": meta.material,
            "machine": meta.machine,
        },
        material_version_id=mv.id if mv else None,
        quantity=quantity,
        model_source_url=model_source_url or None,
        model_source_author=model_source_author or None,
        model_source_license=model_source_license or None,
    )
    session.add(item)
    await session.commit()
    await session.refresh(q)
    return await _quote_out(session, q)


@router.put("/{quote_id}/items/{item_id}", response_model=QuoteOut)
async def update_item(
    quote_id: UUID,
    item_id: UUID,
    payload: QuoteItemUpdate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    it = await session.get(QuoteItem, item_id)
    if not it or it.quote_id != quote_id:
        raise HTTPException(404)
    if payload.name is not None:
        it.name = payload.name
    if payload.quantity is not None:
        if payload.quantity < 1:
            raise HTTPException(400, "quantity must be >= 1")
        it.quantity = payload.quantity
    if payload.material_id is not None:
        try:
            mv = await material_repo.get_by_id(session, UUID(payload.material_id))
        except ValueError:
            raise HTTPException(400, "material_id must be a valid UUID")
        if not mv:
            raise HTTPException(400, "material not found")
        it.material_version_id = mv.id
        meta = dict(it.gcode_meta or {})
        meta["material"] = mv.material_type
        it.gcode_meta = meta
    elif payload.material_code is not None:
        # Back-compat: auto-resolve by polymer type when unique.
        mv = await material_repo.auto_resolve_for_gcode(session, payload.material_code)
        if not mv:
            raise HTTPException(
                400,
                f"cannot uniquely resolve material '{payload.material_code}' "
                "(zero or multiple registered) — send material_id instead",
            )
        it.material_version_id = mv.id
        meta = dict(it.gcode_meta or {})
        meta["material"] = payload.material_code
        it.gcode_meta = meta
    if payload.time_s is not None:
        if payload.time_s < 0:
            raise HTTPException(400, "time_s must be >= 0")
        meta = dict(it.gcode_meta or {})
        meta["time_s"] = float(payload.time_s)
        it.gcode_meta = meta
    if payload.filament_m is not None:
        if payload.filament_m < 0:
            raise HTTPException(400, "filament_m must be >= 0")
        meta = dict(it.gcode_meta or {})
        meta["filament_m"] = float(payload.filament_m)
        it.gcode_meta = meta
    if payload.filament_g is not None:
        if payload.filament_g < 0:
            raise HTTPException(400, "filament_g must be >= 0")
        meta = dict(it.gcode_meta or {})
        if payload.filament_g > 0:
            meta["filament_g"] = float(payload.filament_g)
        else:
            meta.pop("filament_g", None)
        it.gcode_meta = meta
    if payload.is_multi_color is not None:
        it.is_multi_color = bool(payload.is_multi_color)
    if payload.model_source_url is not None:
        it.model_source_url = payload.model_source_url or None
    if payload.model_source_author is not None:
        it.model_source_author = payload.model_source_author or None
    if payload.model_source_license is not None:
        it.model_source_license = payload.model_source_license or None
    await session.commit()
    return await _quote_out(session, q)


@router.post("/{quote_id}/items/{item_id}/reparse", response_model=QuoteOut)
async def reparse_item(
    quote_id: UUID,
    item_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """Re-run the gcode parser over the stored file and replace meta.

    Useful when the parser has been improved since the item was created —
    or when the user just wants to undo a manual override and pull values
    back from the file.
    """
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    it = await session.get(QuoteItem, item_id)
    if not it or it.quote_id != quote_id:
        raise HTTPException(404)
    if not it.filename:
        raise HTTPException(409, "esta peça não tem gcode anexado para reanálise")
    full_path = Path(get_app_settings().storage_dir) / it.filename
    if not full_path.exists():
        raise HTTPException(410, "arquivo gcode original não está mais no disco")
    meta = parse_gcode_metadata(full_path)
    it.gcode_meta = {
        "time_s": meta.time_s,
        "filament_m": meta.filament_m,
        "material": meta.material,
        "machine": meta.machine,
    }
    await session.commit()
    return await _quote_out(session, q)


@router.delete("/{quote_id}/items/{item_id}", response_model=QuoteOut)
async def delete_item(
    quote_id: UUID,
    item_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.DRAFT:
        raise HTTPException(409, "quote not editable")
    it = await session.get(QuoteItem, item_id)
    if not it or it.quote_id != quote_id:
        raise HTTPException(404)
    # Remove os arquivos das fotos do item (o cascade do banco apaga as linhas).
    item_photos = (await session.execute(
        select(QuotePhoto).where(QuotePhoto.quote_item_id == item_id)
    )).scalars().all()
    for p in item_photos:
        photo_storage.delete_photo(p.storage_path)
    await session.delete(it)
    await session.commit()
    return await _quote_out(session, q)
