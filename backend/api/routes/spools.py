from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.spools import SpoolCreate, SpoolUpdate, SpoolOut
from backend.infra.db.models import MaterialConsumption, MaterialVersion, Spool, User
from backend.infra.db.repos import material as material_repo

router = APIRouter()


def _out(s: Spool) -> SpoolOut:
    return SpoolOut(
        id=str(s.id),
        material_version_id=str(s.material_version_id) if s.material_version_id else None,
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
    data = payload.model_dump()
    mv_id_raw = data.pop("material_version_id", None)
    if mv_id_raw is not None:
        # Enviado explicitamente: manda, sem auto-resolve — mas precisa existir.
        try:
            mv_id = UUID(mv_id_raw)
        except ValueError:
            raise HTTPException(400, "material_version_id precisa ser um UUID válido")
        if await session.get(MaterialVersion, mv_id) is None:
            raise HTTPException(400, "material não existe")
        data["material_version_id"] = mv_id
    else:
        # Omitido: mesma regra da migração 0035 — só vincula quando o trio
        # (material_type, color, manufacturer) casa com exatamente UMA versão
        # corrente; caso contrário fica NULL.
        mv = await material_repo.auto_resolve_for_spool(
            session, payload.material_type, payload.color, payload.manufacturer
        )
        data["material_version_id"] = mv.id if mv else None
    s = Spool(**data)
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
    if "material_version_id" in updates:
        raw = updates["material_version_id"]
        if raw is None:
            updates["material_version_id"] = None
        else:
            try:
                mv_id = UUID(raw)
            except ValueError:
                raise HTTPException(400, "material_version_id precisa ser um UUID válido")
            if await session.get(MaterialVersion, mv_id) is None:
                raise HTTPException(400, "material não existe")
            updates["material_version_id"] = mv_id
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
