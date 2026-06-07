from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.services import ServiceCreate, ServiceUpdate, ServiceOut
from backend.infra.db.models import Service, User

router = APIRouter()


def _out(s: Service) -> ServiceOut:
    return ServiceOut(
        id=str(s.id), name=s.name, unit=s.unit, default_rate=s.default_rate,
        kind=s.kind, is_active=s.is_active,
    )


@router.get("", response_model=list[ServiceOut])
async def list_services(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    res = await session.execute(select(Service).order_by(Service.name))
    return [_out(s) for s in res.scalars()]


@router.post("", response_model=ServiceOut, status_code=201)
async def create_service(payload: ServiceCreate, _: User = Depends(require_user),
                         session: AsyncSession = Depends(db_session)):
    s = Service(**payload.model_dump())
    session.add(s); await session.commit(); await session.refresh(s)
    return _out(s)


@router.get("/{service_id}", response_model=ServiceOut)
async def get_service(service_id: UUID, _: User = Depends(require_user),
                      session: AsyncSession = Depends(db_session)):
    s = await session.get(Service, service_id)
    if not s:
        raise HTTPException(404)
    return _out(s)


@router.put("/{service_id}", response_model=ServiceOut)
async def update_service(service_id: UUID, payload: ServiceUpdate, _: User = Depends(require_user),
                         session: AsyncSession = Depends(db_session)):
    s = await session.get(Service, service_id)
    if not s:
        raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await session.commit(); await session.refresh(s)
    return _out(s)


@router.delete("/{service_id}", status_code=204)
async def delete_service(service_id: UUID, _: User = Depends(require_user),
                         session: AsyncSession = Depends(db_session)):
    s = await session.get(Service, service_id)
    if not s:
        raise HTTPException(404)
    await session.delete(s); await session.commit()
