"""Fotos de orçamento: upload, servir bruto, remover.

Movido sem alteração de lógica a partir do antigo `backend/api/routes/quotes.py`.

A rota literal `GET /photos/{photo_id}/raw` precisa ser registrada ANTES das
rotas paramétricas `/{quote_id}` de `crud.py` — ver ordem de include em
`__init__.py`.
"""
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.quotes import QuotePhotoOut
from backend.api.routes.quotes._shared import _photo_out
from backend.infra.db.models import Quote, QuoteItem, QuotePhoto, User
from backend.infra.storage import quote_photos as photo_storage
from backend.settings import get_settings as get_app_settings

router = APIRouter()


# ---------- Fotos ----------


@router.post("/{quote_id}/photos", response_model=QuotePhotoOut)
async def add_photo(
    quote_id: UUID,
    file: UploadFile = File(...),
    quote_item_id: str | None = Form(None),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    item_uuid = None
    if quote_item_id:
        item_uuid = UUID(quote_item_id)
        it = await session.get(QuoteItem, item_uuid)
        if it is None or it.quote_id != q.id:
            raise HTTPException(400, "item não pertence ao orçamento")
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(413, "imagem maior que 15MB")
    try:
        saved = photo_storage.save_photo(content, file.filename or "foto.jpg")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    cond = QuotePhoto.quote_item_id.is_(None) if item_uuid is None else (QuotePhoto.quote_item_id == item_uuid)
    siblings = (await session.execute(
        select(QuotePhoto).where(QuotePhoto.quote_id == q.id, cond)
    )).scalars().all()
    photo = QuotePhoto(
        quote_id=q.id, quote_item_id=item_uuid,
        storage_path=saved.storage_path, content_type=saved.content_type,
        size_bytes=saved.size_bytes, width=saved.width, height=saved.height,
        sort_order=len(siblings),
    )
    session.add(photo)
    await session.commit()
    await session.refresh(photo)
    return _photo_out(photo)


@router.get("/photos/{photo_id}/raw")
async def serve_photo(photo_id: UUID, session: AsyncSession = Depends(db_session)):
    p = await session.get(QuotePhoto, photo_id)
    if not p:
        raise HTTPException(404)
    full = Path(get_app_settings().storage_dir) / p.storage_path
    if not full.exists():
        raise HTTPException(404)
    return FileResponse(full, media_type=p.content_type)


@router.delete("/{quote_id}/photos/{photo_id}", status_code=204)
async def delete_photo(
    quote_id: UUID, photo_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    p = await session.get(QuotePhoto, photo_id)
    if p is None or p.quote_id != quote_id:
        raise HTTPException(404)
    photo_storage.delete_photo(p.storage_path)
    await session.delete(p)
    await session.commit()
    return Response(status_code=204)
