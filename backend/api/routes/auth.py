from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.auth import LoginRequest, MeResponse
from backend.core.security import verify_password, make_jwt
from backend.infra.db.models import User
from backend.settings import get_settings

router = APIRouter()


@router.post("/login")
async def login(payload: LoginRequest, response: Response,
                session: AsyncSession = Depends(db_session)):
    res = await session.execute(select(User).where(User.email == payload.email))
    user = res.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = make_jwt(sub=str(user.id), secret=get_settings().session_secret)
    response.set_cookie("session", token, httponly=True, samesite="lax", max_age=7 * 24 * 3600)
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(require_user)):
    return MeResponse(id=str(user.id), name=user.name, email=user.email)
