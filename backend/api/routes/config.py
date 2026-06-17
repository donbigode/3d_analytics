"""Configuration endpoints — provider API keys + toggles.

Kept separate from /settings to avoid leaking key material into the
existing settings GET response.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.config import (
    ExportConfigOut,
    ExportConfigUpdate,
    ProvidersOut,
    ProvidersUpdate,
)
from backend.core.export.runner import execute_export
from backend.infra.db.models import ExportConfig, Settings, User

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
    reddit_active = bool(
        s.reddit_access_token
        and s.reddit_token_expires_at
        and s.reddit_token_expires_at > datetime.now(timezone.utc)
    )
    return ProvidersOut(
        preferred_llm_provider=s.preferred_llm_provider,
        llm_suggestions_enabled=s.llm_suggestions_enabled,
        digest_auto_enabled=s.digest_auto_enabled,
        anthropic_configured=bool(s.anthropic_api_key),
        anthropic_key_preview=_mask(s.anthropic_api_key),
        gemini_configured=bool(s.gemini_api_key),
        gemini_key_preview=_mask(s.gemini_api_key),
        openai_configured=bool(s.openai_api_key),
        openai_key_preview=_mask(s.openai_api_key),
        meli_configured=bool(s.meli_app_id and s.meli_client_secret),
        meli_app_id_preview=_mask(s.meli_app_id),
        meli_secret_preview=_mask(s.meli_client_secret),
        meli_token_active=meli_active,
        reddit_configured=bool(s.reddit_client_id and s.reddit_client_secret),
        reddit_client_id_preview=_mask(s.reddit_client_id),
        reddit_secret_preview=_mask(s.reddit_client_secret),
        reddit_token_active=reddit_active,
        youtube_configured=bool(s.youtube_api_key),
        youtube_key_preview=_mask(s.youtube_api_key),
    )


async def _get_export_cfg(session: AsyncSession) -> ExportConfig:
    cfg = await session.get(ExportConfig, 1)
    if cfg is None:
        cfg = ExportConfig(id=1)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


def _export_out(c: ExportConfig) -> ExportConfigOut:
    return ExportConfigOut(
        enabled=c.enabled, destination=c.destination,
        s3_bucket=c.s3_bucket, s3_region=c.s3_region, s3_prefix=c.s3_prefix,
        s3_access_key_id=c.s3_access_key_id,
        s3_secret_configured=bool(c.s3_secret_access_key),
        s3_secret_access_key_preview=_mask(c.s3_secret_access_key),
        databricks_host=c.databricks_host, databricks_volume_path=c.databricks_volume_path,
        databricks_token_configured=bool(c.databricks_token),
        databricks_token_preview=_mask(c.databricks_token),
        last_run_at=c.last_run_at.isoformat() if c.last_run_at else None,
        last_run_status=c.last_run_status, last_run_detail=c.last_run_detail,
    )


@router.get("/export", response_model=ExportConfigOut)
async def get_export_config(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    return _export_out(await _get_export_cfg(session))


@router.put("/export", response_model=ExportConfigOut)
async def put_export_config(payload: ExportConfigUpdate, _: User = Depends(require_user),
                            session: AsyncSession = Depends(db_session)):
    c = await _get_export_cfg(session)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k in ("s3_secret_access_key", "databricks_token"):
            # segredo só é sobrescrito quando vier um valor; vazio = não altera
            if v:
                setattr(c, k, v)
        else:
            setattr(c, k, v if v != "" else None)
    await session.commit(); await session.refresh(c)
    return _export_out(c)


@router.post("/export/run")
async def run_export_now(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    return await execute_export(session)


@router.put("/providers", response_model=ProvidersOut)
async def put_providers(
    payload: ProvidersUpdate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    s = await _get_settings_row(session)
    if payload.preferred_llm_provider is not None:
        if payload.preferred_llm_provider not in {"anthropic", "gemini", "openai"}:
            raise HTTPException(400, "preferred_llm_provider must be 'anthropic', 'gemini' or 'openai'")
        s.preferred_llm_provider = payload.preferred_llm_provider
    if payload.llm_suggestions_enabled is not None:
        s.llm_suggestions_enabled = payload.llm_suggestions_enabled
    if payload.digest_auto_enabled is not None:
        s.digest_auto_enabled = payload.digest_auto_enabled
    # Keys: "" clears, None leaves alone, any other string sets.
    if payload.anthropic_api_key is not None:
        s.anthropic_api_key = payload.anthropic_api_key or None
    if payload.gemini_api_key is not None:
        s.gemini_api_key = payload.gemini_api_key or None
    if payload.openai_api_key is not None:
        s.openai_api_key = payload.openai_api_key or None
    if payload.meli_app_id is not None:
        s.meli_app_id = payload.meli_app_id or None
        # Clear cached token when credentials change so next collect refreshes.
        s.meli_access_token = None
        s.meli_token_expires_at = None
    if payload.meli_client_secret is not None:
        s.meli_client_secret = payload.meli_client_secret or None
        s.meli_access_token = None
        s.meli_token_expires_at = None
    if payload.reddit_client_id is not None:
        s.reddit_client_id = payload.reddit_client_id or None
        s.reddit_access_token = None
        s.reddit_token_expires_at = None
    if payload.reddit_client_secret is not None:
        s.reddit_client_secret = payload.reddit_client_secret or None
        s.reddit_access_token = None
        s.reddit_token_expires_at = None
    if payload.youtube_api_key is not None:
        s.youtube_api_key = payload.youtube_api_key or None
    await session.commit()
    await session.refresh(s)
    meli_active = bool(
        s.meli_access_token
        and s.meli_token_expires_at
        and s.meli_token_expires_at > datetime.now(timezone.utc)
    )
    reddit_active = bool(
        s.reddit_access_token
        and s.reddit_token_expires_at
        and s.reddit_token_expires_at > datetime.now(timezone.utc)
    )
    return ProvidersOut(
        preferred_llm_provider=s.preferred_llm_provider,
        llm_suggestions_enabled=s.llm_suggestions_enabled,
        digest_auto_enabled=s.digest_auto_enabled,
        anthropic_configured=bool(s.anthropic_api_key),
        anthropic_key_preview=_mask(s.anthropic_api_key),
        gemini_configured=bool(s.gemini_api_key),
        gemini_key_preview=_mask(s.gemini_api_key),
        openai_configured=bool(s.openai_api_key),
        openai_key_preview=_mask(s.openai_api_key),
        meli_configured=bool(s.meli_app_id and s.meli_client_secret),
        meli_app_id_preview=_mask(s.meli_app_id),
        meli_secret_preview=_mask(s.meli_client_secret),
        meli_token_active=meli_active,
        reddit_configured=bool(s.reddit_client_id and s.reddit_client_secret),
        reddit_client_id_preview=_mask(s.reddit_client_id),
        reddit_secret_preview=_mask(s.reddit_client_secret),
        reddit_token_active=reddit_active,
        youtube_configured=bool(s.youtube_api_key),
        youtube_key_preview=_mask(s.youtube_api_key),
    )
