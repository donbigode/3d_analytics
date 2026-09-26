"""Itens de orçamento: adicionar, atualizar, reanalisar gcode, remover.

Movido sem alteração de lógica a partir do antigo `backend/api/routes/quotes.py`.
"""
import logging
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.quotes import QuoteItemUpdate, QuoteOut
from backend.api.routes.quotes._shared import _quote_out
from backend.core.gcode.parser import GcodeMeta, parse_gcode_metadata
from backend.core.models import QuoteStatus
from backend.core.quotes.filaments import validate_lines
from backend.infra.db.models import (
    MaterialVersion,
    Quote,
    QuoteItem,
    QuoteItemFilament,
    QuotePhoto,
    User,
)
from backend.infra.db.repos import material as material_repo
from backend.infra.storage import quote_photos as photo_storage
from backend.infra.storage.gcodes import save_gcode
from backend.settings import get_settings as get_app_settings

logger = logging.getLogger(__name__)

router = APIRouter()


async def _sync_linha1(session: AsyncSession, item_id: UUID, material_version_id: UUID) -> None:
    """Garante a linha de ``position = 1`` do item apontando para o material.

    Todo item com material resolvido precisa de pelo menos uma linha: é a
    tabela autoritativa do custo, e sem linha ``_build_item_input`` devolve
    ``None`` e a peça para de orçar em silêncio. Cria quando o item era
    pendente; troca o material quando já existia (não duplica, e as linhas
    2..N de um item multicor ficam onde estão).
    """
    linha1 = (
        await session.execute(
            select(QuoteItemFilament)
            .where(QuoteItemFilament.quote_item_id == item_id)
            .where(QuoteItemFilament.position == 1)
        )
    ).scalar_one_or_none()
    if linha1 is None:
        session.add(QuoteItemFilament(
            quote_item_id=item_id,
            material_version_id=material_version_id,
            grams_unit=None,
            position=1,
        ))
    else:
        linha1.material_version_id = material_version_id


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
    # flush para ter o id do item antes de pendurar a linha de filamento nele
    await session.flush()
    if item.material_version_id is not None:
        # Item que entra pendente (sem material) NÃO ganha linha — a invariante
        # é "item com material resolvido tem ao menos uma linha".
        session.add(QuoteItemFilament(
            quote_item_id=item.id,
            material_version_id=item.material_version_id,
            grams_unit=None,
            position=1,
        ))
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

    if payload.filaments is not None and payload.material_id is not None:
        raise HTTPException(
            400,
            "envie material_id OU filaments, não os dois — material_id é o "
            "atalho para um item de uma cor e reescreve a linha 1",
        )

    if payload.filaments is not None:
        novas = []
        # As MaterialVersion na mesma ordem das linhas. `mv` do loop é a da
        # ÚLTIMA linha; quem define o material do item é a linha 1.
        mvs = []
        for pos, linha in enumerate(payload.filaments, start=1):
            try:
                mv_id = UUID(linha.material_id)
            except ValueError:
                raise HTTPException(400, "material_id must be a valid UUID")
            mv = await session.get(MaterialVersion, mv_id)
            if mv is None:
                raise HTTPException(400, f"material {linha.material_id} não existe")
            mvs.append(mv)
            novas.append(
                QuoteItemFilament(
                    quote_item_id=it.id,
                    material_version_id=mv.id,
                    grams_unit=linha.grams_unit,
                    position=pos,
                )
            )
        try:
            validate_lines(novas)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        # Apagar e recriar, não fazer diff: a UNIQUE (quote_item_id, position)
        # faz um update em ordem colidir consigo mesmo no meio do caminho, e a
        # substituição é o contrato declarado.
        await session.execute(
            delete(QuoteItemFilament).where(QuoteItemFilament.quote_item_id == it.id)
        )
        await session.flush()
        session.add_all(novas)
        await session.flush()
        # Derivado (invariante 2)
        it.material_version_id = novas[0].material_version_id
        # E `gcode_meta["material"]` acompanha a linha 1, exatamente como no
        # branch de `material_id` abaixo. Sem isto, escolher material só pelas
        # linhas deixava ali a string crua do fatiador (ex. "Generic PLA"), que
        # não é um `material_type` — e nove consumidores leem esse campo, entre
        # eles o `material_polymer` do PDF, os prompts de markup/variantes e o
        # filtro de bobina da tela de produzir, que passava a não casar com
        # nada. Linha 1 é o material do item por convenção declarada — é o
        # mesmo significado de `quote_items.material_version_id`.
        # JSONB: reatribui um dict novo, senão o SQLAlchemy não vê a mudança.
        meta = dict(it.gcode_meta or {})
        meta["material"] = mvs[0].material_type
        it.gcode_meta = meta

    if payload.material_id is not None:
        try:
            mv = await material_repo.get_by_id(session, UUID(payload.material_id))
        except ValueError:
            raise HTTPException(400, "material_id must be a valid UUID")
        if not mv:
            raise HTTPException(400, "material not found")
        await _sync_linha1(session, it.id, mv.id)
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
        await _sync_linha1(session, it.id, mv.id)
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
