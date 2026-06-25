from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.people import PersonCreate, PersonOut, PersonUpdate
from backend.infra.db.models import Person, User

router = APIRouter()


def _out(p: Person) -> PersonOut:
    return PersonOut(id=str(p.id), name=p.name, active=p.active, sort_order=p.sort_order)


@router.get("", response_model=list[PersonOut])
async def list_people(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    rows = (await session.execute(select(Person).order_by(Person.sort_order, Person.name))).scalars().all()
    return [_out(p) for p in rows]


@router.post("", response_model=PersonOut, status_code=201)
async def create_person(payload: PersonCreate, _: User = Depends(require_user),
                        session: AsyncSession = Depends(db_session)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "nome vazio")
    exists = (await session.execute(select(Person).where(Person.name == name))).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "já existe pessoa com esse nome")
    p = Person(name=name)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return _out(p)


@router.put("/{person_id}", response_model=PersonOut)
async def update_person(person_id: UUID, payload: PersonUpdate, _: User = Depends(require_user),
                        session: AsyncSession = Depends(db_session)):
    p = await session.get(Person, person_id)
    if not p:
        raise HTTPException(404)
    if payload.name is not None:
        p.name = payload.name.strip()
    if payload.active is not None:
        p.active = payload.active
    if payload.sort_order is not None:
        p.sort_order = payload.sort_order
    await session.commit()
    await session.refresh(p)
    return _out(p)


@router.delete("/{person_id}", status_code=204)
async def delete_person(person_id: UUID, _: User = Depends(require_user),
                        session: AsyncSession = Depends(db_session)):
    p = await session.get(Person, person_id)
    if not p:
        raise HTTPException(404)
    await session.delete(p)
    await session.commit()
    return Response(status_code=204)
