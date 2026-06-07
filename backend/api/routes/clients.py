from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.clients import ClientCreate, ClientUpdate, ClientOut
from backend.infra.db.models import Client, User

router = APIRouter()


@router.get("", response_model=list[ClientOut])
async def list_clients(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    res = await session.execute(select(Client).order_by(Client.name))
    return [ClientOut(id=str(c.id), name=c.name, phone=c.phone, email=c.email, notes=c.notes)
            for c in res.scalars()]


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(payload: ClientCreate, _: User = Depends(require_user),
                        session: AsyncSession = Depends(db_session)):
    c = Client(**payload.model_dump())
    session.add(c); await session.commit(); await session.refresh(c)
    return ClientOut(id=str(c.id), name=c.name, phone=c.phone, email=c.email, notes=c.notes)


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(client_id: UUID, _: User = Depends(require_user),
                     session: AsyncSession = Depends(db_session)):
    c = await session.get(Client, client_id)
    if not c:
        raise HTTPException(404)
    return ClientOut(id=str(c.id), name=c.name, phone=c.phone, email=c.email, notes=c.notes)


@router.put("/{client_id}", response_model=ClientOut)
async def update_client(client_id: UUID, payload: ClientUpdate, _: User = Depends(require_user),
                        session: AsyncSession = Depends(db_session)):
    c = await session.get(Client, client_id)
    if not c:
        raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    await session.commit(); await session.refresh(c)
    return ClientOut(id=str(c.id), name=c.name, phone=c.phone, email=c.email, notes=c.notes)


@router.delete("/{client_id}", status_code=204)
async def delete_client(client_id: UUID, _: User = Depends(require_user),
                        session: AsyncSession = Depends(db_session)):
    c = await session.get(Client, client_id)
    if not c:
        raise HTTPException(404)
    await session.delete(c); await session.commit()
