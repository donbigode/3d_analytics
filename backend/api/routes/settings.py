from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path

from backend.api.deps import db_session, require_user
from backend.api.schemas.settings import SettingsIn, SettingsOut
from backend.infra.db.models import Settings, User
from backend.infra.storage import branding
from backend.settings import get_settings as get_app_settings

router = APIRouter()


async def _get_or_create(session: AsyncSession) -> Settings:
    s = await session.get(Settings, 1)
    if not s:
        s = Settings(id=1)
        session.add(s); await session.commit(); await session.refresh(s)
    return s


def _out(s: Settings) -> SettingsOut:
    return SettingsOut(**{c.name: getattr(s, c.name) for c in Settings.__table__.columns if c.name != "id"})


@router.get("", response_model=SettingsOut)
async def get_settings_endpoint(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    return _out(await _get_or_create(session))


@router.put("", response_model=SettingsOut)
async def update_settings(payload: SettingsIn, _: User = Depends(require_user),
                          session: AsyncSession = Depends(db_session)):
    s = await _get_or_create(session)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await session.commit(); await session.refresh(s)
    return _out(s)


@router.post("/logo", response_model=SettingsOut)
async def upload_logo(file: UploadFile = File(...), _: User = Depends(require_user),
                      session: AsyncSession = Depends(db_session)):
    content = await file.read()
    try:
        path = branding.save_logo(file.filename or "logo.png", content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    s = await _get_or_create(session)
    s.logo_path = path
    await session.commit(); await session.refresh(s)
    return _out(s)


@router.delete("/logo", response_model=SettingsOut)
async def remove_logo(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    s = await _get_or_create(session)
    branding.delete_logo(s.logo_path)
    s.logo_path = None
    await session.commit(); await session.refresh(s)
    return _out(s)


@router.get("/logo")
async def serve_logo(session: AsyncSession = Depends(db_session)):
    s = await _get_or_create(session)
    if not s.logo_path:
        raise HTTPException(404)
    full = Path(get_app_settings().storage_dir) / s.logo_path
    return FileResponse(full)
