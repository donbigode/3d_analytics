"""Material endpoints — UUID-keyed access.

Each registered material is identified by its UUID. ``material_type`` is the
polymer family used to match gcode headers; ``manufacturer`` and ``color``
distinguish concrete products of the same type. SCD2 versioning is per
product line: editing a material closes the current row and opens a new one
with the same (type, manufacturer, color) trio.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.materials import MaterialCreate, MaterialOut, MaterialUpdate
from backend.infra.db.models import MaterialVersion, QuoteItem, User
from backend.infra.db.repos import material as repo

router = APIRouter()


def _out(mv: MaterialVersion) -> MaterialOut:
    return MaterialOut(
        id=str(mv.id),
        material_type=mv.material_type,
        name=mv.name,
        manufacturer=mv.manufacturer,
        color=mv.color,
        density_g_cm3=mv.density_g_cm3,
        price_per_kg_ref=mv.price_per_kg_ref,
        failure_rate_pct=mv.failure_rate_pct,
        is_current=mv.is_current,
        effective_from=mv.effective_from,
        effective_to=mv.effective_to,
    )


@router.get("", response_model=list[MaterialOut])
async def list_materials(
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session)
):
    return [_out(m) for m in await repo.list_current(session)]


@router.post("", response_model=MaterialOut, status_code=201)
async def create_material(
    payload: MaterialCreate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    mv = await repo.create_initial(session, **payload.model_dump())
    return _out(mv)


@router.get("/{material_id}", response_model=MaterialOut)
async def get_material(
    material_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    mv = await repo.get_by_id(session, material_id)
    if not mv:
        raise HTTPException(404)
    return _out(mv)


@router.get("/{material_id}/history", response_model=list[MaterialOut])
async def material_history(
    material_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    versions = await repo.history(session, material_id)
    if not versions:
        raise HTTPException(404)
    return [_out(v) for v in versions]


@router.put("/{material_id}", response_model=MaterialOut)
async def update_material(
    material_id: UUID,
    payload: MaterialUpdate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "no fields to update")
    try:
        mv = await repo.new_version(session, material_id, **changes)
    except ValueError:
        raise HTTPException(404)
    return _out(mv)


@router.delete("/{material_id}", status_code=204)
async def delete_material(
    material_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    versions = await repo.history(session, material_id)
    if not versions:
        raise HTTPException(404)
    version_ids = [v.id for v in versions]
    in_use = await session.scalar(
        select(exists().where(QuoteItem.material_version_id.in_(version_ids)))
    )
    if in_use:
        raise HTTPException(409, "material has been referenced; cannot hard-delete")
    for v in versions:
        await session.delete(v)
    await session.commit()
