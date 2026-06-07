from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.materials import MaterialCreate, MaterialUpdate, MaterialOut
from backend.infra.db.models import MaterialVersion, QuoteItem, User
from backend.infra.db.repos import material as repo

router = APIRouter()


def _out(mv: MaterialVersion) -> MaterialOut:
    return MaterialOut(
        id=str(mv.id), material_code=mv.material_code, name=mv.name,
        density_g_cm3=mv.density_g_cm3, price_per_kg_ref=mv.price_per_kg_ref,
        failure_rate_pct=mv.failure_rate_pct, is_current=mv.is_current,
        effective_from=mv.effective_from, effective_to=mv.effective_to,
    )


@router.get("", response_model=list[MaterialOut])
async def list_materials(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    return [_out(m) for m in await repo.list_current(session)]


@router.post("", response_model=MaterialOut, status_code=201)
async def create_material(payload: MaterialCreate, _: User = Depends(require_user),
                          session: AsyncSession = Depends(db_session)):
    try:
        mv = await repo.create_initial(session, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _out(mv)


@router.get("/{code}", response_model=MaterialOut)
async def get_material(code: str, _: User = Depends(require_user),
                       session: AsyncSession = Depends(db_session)):
    mv = await repo.current(session, code)
    if not mv:
        raise HTTPException(404)
    return _out(mv)


@router.get("/{code}/history", response_model=list[MaterialOut])
async def material_history(code: str, _: User = Depends(require_user),
                           session: AsyncSession = Depends(db_session)):
    versions = await repo.history(session, code)
    if not versions:
        raise HTTPException(404)
    return [_out(v) for v in versions]


@router.put("/{code}", response_model=MaterialOut)
async def update_material(code: str, payload: MaterialUpdate, _: User = Depends(require_user),
                          session: AsyncSession = Depends(db_session)):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "no fields to update")
    try:
        mv = await repo.new_version(session, code, **changes)
    except ValueError:
        raise HTTPException(404)
    return _out(mv)


@router.delete("/{code}", status_code=204)
async def delete_material(code: str, _: User = Depends(require_user),
                          session: AsyncSession = Depends(db_session)):
    versions = await repo.history(session, code)
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
