from collections.abc import AsyncIterator
from uuid import UUID
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import decode_jwt
from backend.infra.db.session import get_session
from backend.infra.db.models import User
from backend.settings import get_settings


async def db_session() -> AsyncIterator[AsyncSession]:
    async for s in get_session():
        yield s


async def require_user(request: Request, session: AsyncSession = Depends(db_session)) -> User:
    token = request.cookies.get("session")
    if not token:
        raise HTTPException(401, "not authenticated")
    try:
        claims = decode_jwt(token, get_settings().session_secret)
    except Exception:
        raise HTTPException(401, "invalid session")
    user_id = UUID(claims["sub"])
    u = await session.get(User, user_id)
    if not u:
        raise HTTPException(401, "user not found")
    return u
