from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.users import UserCreate, UserOut
from backend.core.security import hash_password
from backend.infra.db.models import User

router = APIRouter()


@router.get("", response_model=list[UserOut])
async def list_users(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    res = await session.execute(select(User).order_by(User.created_at))
    return [UserOut(id=str(u.id), name=u.name, email=u.email) for u in res.scalars()]


@router.post("", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate, _: User = Depends(require_user),
                      session: AsyncSession = Depends(db_session)):
    u = User(name=payload.name, email=payload.email, password_hash=hash_password(payload.password))
    session.add(u); await session.commit(); await session.refresh(u)
    return UserOut(id=str(u.id), name=u.name, email=u.email)


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: UUID, _: User = Depends(require_user),
                      session: AsyncSession = Depends(db_session)):
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(404)
    await session.delete(u); await session.commit()
