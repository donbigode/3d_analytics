"""Library endpoints — local asset CRUD, remote search, programmatic download.

The route module deliberately stays thin: business logic (parse, dedup,
fetch from remote) lives in :mod:`backend.core.library` so it stays
testable.
"""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.library import (
    AssetOut,
    AssetUpdate,
    DownloadOut,
    DownloadRequest,
    RemoteSearchHit,
    SearchResponse,
)
from backend.core.library import (
    LibrarySaveError,
    compute_hash,
    detect_format,
    parse_meta_for_format,
    save_bytes,
    storage_path_for,
)
from backend.infra.db.models import Asset, User
from backend.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _out(a: Asset) -> AssetOut:
    return AssetOut(
        id=str(a.id),
        filename=a.filename,
        format=a.format,
        size_bytes=a.size_bytes,
        file_hash=a.file_hash,
        parsed_meta=a.parsed_meta,
        source_url=a.source_url,
        source_site=a.source_site,
        source_author=a.source_author,
        source_license=a.source_license,
        thumbnail_url=a.thumbnail_url,
        tags=a.tags,
        notes=a.notes,
        created_at=a.created_at,
    )


# ---------- list ----------

@router.get("", response_model=list[AssetOut])
async def list_assets(
    fmt: str | None = Query(None),
    source_site: str | None = Query(None),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    stmt = select(Asset).order_by(desc(Asset.created_at))
    if fmt:
        stmt = stmt.where(Asset.format == fmt)
    if source_site:
        stmt = stmt.where(Asset.source_site == source_site)
    res = await session.execute(stmt)
    return [_out(a) for a in res.scalars()]


# ---------- upload ----------

@router.post("/upload", response_model=DownloadOut, status_code=201)
async def upload_asset(
    file: UploadFile = File(...),
    source_url: str | None = Form(None),
    source_author: str | None = Form(None),
    source_license: str | None = Form(None),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    fmt = detect_format(file.filename or "")
    if not fmt:
        raise HTTPException(
            400, "unsupported format — expected one of .gcode / .3mf / .stl / .bgcode"
        )

    content = await file.read()
    if not content:
        raise HTTPException(400, "empty file")

    digest = compute_hash(content)

    # Dedup
    existing = (
        await session.execute(select(Asset).where(Asset.file_hash == digest))
    ).scalar_one_or_none()
    if existing:
        return DownloadOut(asset=_out(existing), duplicate=True)

    try:
        path, _h = save_bytes(content, fmt=fmt, file_hash=digest)
    except LibrarySaveError as exc:
        raise HTTPException(500, f"cannot persist file: {exc}")

    rel_path = str(path.relative_to(get_settings().storage_dir))
    meta = parse_meta_for_format(content, fmt)
    asset = Asset(
        filename=file.filename or f"{digest[:8]}.{fmt}",
        format=fmt,
        size_bytes=len(content),
        file_hash=digest,
        storage_path=rel_path,
        parsed_meta=meta or None,
        source_url=source_url or None,
        source_site="manual",
        source_author=source_author or None,
        source_license=source_license or None,
    )
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return DownloadOut(asset=_out(asset), duplicate=False)


# ---------- delete ----------

@router.delete("/{asset_id}", status_code=204)
async def delete_asset(
    asset_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    a = await session.get(Asset, asset_id)
    if not a:
        raise HTTPException(404)
    # remove the file from disk too (idempotent — if it's already gone, no big deal)
    full = Path(get_settings().storage_dir) / a.storage_path
    try:
        if full.exists():
            full.unlink()
    except OSError as exc:
        logger.warning("could not unlink %s: %s", full, exc)
    await session.delete(a)
    await session.commit()


# ---------- update meta ----------

@router.put("/{asset_id}", response_model=AssetOut)
async def update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    a = await session.get(Asset, asset_id)
    if not a:
        raise HTTPException(404)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    await session.commit()
    await session.refresh(a)
    return _out(a)


# ---------- serve binary ----------

@router.get("/{asset_id}/file")
async def serve_asset(
    asset_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    a = await session.get(Asset, asset_id)
    if not a:
        raise HTTPException(404)
    full = Path(get_settings().storage_dir) / a.storage_path
    if not full.exists():
        raise HTTPException(410, "file missing on disk")
    return FileResponse(full, filename=a.filename)


# ---------- remote search (stub for now, filled by Bloco 2) ----------

@router.post("/search", response_model=SearchResponse)
async def search_remote(
    payload: dict,
    _: User = Depends(require_user),
):
    # Bloco 2 plugs Printables here; Bloco 3 adds Thingiverse.
    return SearchResponse(query=str(payload.get("q") or ""), hits=[], errors=[
        "remote search not implemented yet — coming in Bloco 2"
    ])


@router.post("/download", response_model=DownloadOut, status_code=201)
async def download_remote(
    payload: DownloadRequest,
    _: User = Depends(require_user),
):
    raise HTTPException(501, "remote download not implemented yet — coming in Bloco 2")
