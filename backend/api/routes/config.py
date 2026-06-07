"""Configuration endpoints — provider API keys + toggles.

Kept separate from /settings to avoid leaking key material into the
existing settings GET response.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.config import ProvidersOut, ProvidersUpdate
from backend.infra.db.models import Settings, User

router = APIRouter()


def _mask(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"


async def _get_settings_row(session: AsyncSession) -> Settings:
    s = await session.get(Settings, 1)
    if s is None:
        s = Settings(id=1)
        session.add(s)
        await session.commit()
        await session.refresh(s)
    return s


@router.get("/providers", response_model=ProvidersOut)
async def get_providers(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    s = await _get_settings_row(session)
    meli_active = bool(
        s.meli_access_token
        and s.meli_token_expires_at
        and s.meli_token_expires_at > datetime.now(timezone.utc)
    )
    return ProvidersOut(
        preferred_llm_provider=s.preferred_llm_provider,
        llm_suggestions_enabled=s.llm_suggestions_enabled,
        anthropic_configured=bool(s.anthropic_api_key),
        anthropic_key_preview=_mask(s.anthropic_api_key),
        gemini_configured=bool(s.gemini_api_key),
        gemini_key_preview=_mask(s.gemini_api_key),
        meli_configured=bool(s.meli_app_id and s.meli_client_secret),
        meli_app_id_preview=_mask(s.meli_app_id),
        meli_secret_preview=_mask(s.meli_client_secret),
        meli_token_active=meli_active,
    )


@router.put("/providers", response_model=ProvidersOut)
async def put_providers(
    payload: ProvidersUpdate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    s = await _get_settings_row(session)
    if payload.preferred_llm_provider is not None:
        if payload.preferred_llm_provider not in {"anthropic", "gemini"}:
            raise HTTPException(400, "preferred_llm_provider must be 'anthropic' or 'gemini'")
        s.preferred_llm_provider = payload.preferred_llm_provider
    if payload.llm_suggestions_enabled is not None:
        s.llm_suggestions_enabled = payload.llm_suggestions_enabled
    # Keys: "" clears, None leaves alone, any other string sets.
    if payload.anthropic_api_key is not None:
        s.anthropic_api_key = payload.anthropic_api_key or None
    if payload.gemini_api_key is not None:
        s.gemini_api_key = payload.gemini_api_key or None
    if payload.meli_app_id is not None:
        s.meli_app_id = payload.meli_app_id or None
        # Clear cached token when credentials change so next collect refreshes.
        s.meli_access_token = None
        s.meli_token_expires_at = None
    if payload.meli_client_secret is not None:
        s.meli_client_secret = payload.meli_client_secret or None
        s.meli_access_token = None
        s.meli_token_expires_at = None
    await session.commit()
    await session.refresh(s)
    meli_active = bool(
        s.meli_access_token
        and s.meli_token_expires_at
        and s.meli_token_expires_at > datetime.now(timezone.utc)
    )
    return ProvidersOut(
        preferred_llm_provider=s.preferred_llm_provider,
        llm_suggestions_enabled=s.llm_suggestions_enabled,
        anthropic_configured=bool(s.anthropic_api_key),
        anthropic_key_preview=_mask(s.anthropic_api_key),
        gemini_configured=bool(s.gemini_api_key),
        gemini_key_preview=_mask(s.gemini_api_key),
        meli_configured=bool(s.meli_app_id and s.meli_client_secret),
        meli_app_id_preview=_mask(s.meli_app_id),
        meli_secret_preview=_mask(s.meli_client_secret),
        meli_token_active=meli_active,
    )
