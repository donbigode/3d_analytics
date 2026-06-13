from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.spools import SpoolCreate, SpoolUpdate, SpoolOut
from backend.infra.db.models import MaterialConsumption, Spool, User

router = APIRouter()


def _out(s: Spool) -> SpoolOut:
    return SpoolOut(
        id=str(s.id),
        material_type=s.material_type,
        color=s.color,
        manufacturer=s.manufacturer,
        purchased_from=s.purchased_from,
        purchase_url=s.purchase_url,
        purchased_at=s.purchased_at,
        purchased_price=s.purchased_price,
        initial_grams=s.initial_grams,
        remaining_grams=s.remaining_grams,
        status=s.status,
        notes=s.notes,
    )


@router.get("", response_model=list[SpoolOut])
async def list_spools(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    res = await session.execute(select(Spool).order_by(Spool.purchased_at.desc()))
    return [_out(s) for s in res.scalars()]


@router.post("", response_model=SpoolOut, status_code=201)
async def create_spool(payload: SpoolCreate, _: User = Depends(require_user),
                       session: AsyncSession = Depends(db_session)):
    if payload.remaining_grams > payload.initial_grams:
        raise HTTPException(400, "remaining_grams cannot exceed initial_grams")
    s = Spool(**payload.model_dump())
    session.add(s); await session.commit(); await session.refresh(s)
    return _out(s)


@router.get("/{spool_id}", response_model=SpoolOut)
async def get_spool(spool_id: UUID, _: User = Depends(require_user),
                    session: AsyncSession = Depends(db_session)):
    s = await session.get(Spool, spool_id)
    if not s:
        raise HTTPException(404)
    return _out(s)


@router.put("/{spool_id}", response_model=SpoolOut)
async def update_spool(spool_id: UUID, payload: SpoolUpdate, _: User = Depends(require_user),
                       session: AsyncSession = Depends(db_session)):
    s = await session.get(Spool, spool_id)
    if not s:
        raise HTTPException(404)
    updates = payload.model_dump(exclude_unset=True)
    # check post-update invariant: remaining <= initial
    new_initial = updates.get("initial_grams", s.initial_grams)
    new_remaining = updates.get("remaining_grams", s.remaining_grams)
    if new_remaining > new_initial:
        raise HTTPException(400, "remaining_grams cannot exceed initial_grams")
    for k, v in updates.items():
        setattr(s, k, v)
    await session.commit(); await session.refresh(s)
    return _out(s)


@router.delete("/{spool_id}", status_code=204)
async def delete_spool(spool_id: UUID, _: User = Depends(require_user),
                       session: AsyncSession = Depends(db_session)):
    s = await session.get(Spool, spool_id)
    if not s:
        raise HTTPException(404)
    consumed = await session.scalar(
        select(exists().where(MaterialConsumption.spool_id == spool_id))
    )
    if consumed:
        raise HTTPException(
            409,
            "spool already debited by a produced quote; mark it as 'discarded' "
            "instead of deleting to keep the consumption history",
        )
    await session.delete(s); await session.commit()
