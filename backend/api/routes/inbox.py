from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.inbox import InboxPromote
from backend.core.models import QuoteStatus, WatcherInboxStatus
from backend.infra.db.models import Quote, QuoteItem, User, WatcherInboxFile
from backend.infra.db.repos import material as material_repo

router = APIRouter()


@router.get("")
async def list_inbox(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    rows = (
        await session.execute(
            select(WatcherInboxFile)
            .where(WatcherInboxFile.status == WatcherInboxStatus.PENDING)
            .order_by(WatcherInboxFile.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "original_path": r.original_path,
            "parsed_meta": r.parsed_meta,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/{inbox_id}/promote")
async def promote(
    inbox_id: UUID,
    payload: InboxPromote,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    rec = await session.get(WatcherInboxFile, inbox_id)
    if not rec or rec.status != WatcherInboxStatus.PENDING:
        raise HTTPException(404)
    mat_type = (rec.parsed_meta or {}).get("material") or "PLA"
    # Auto-resolve only when unique; otherwise the new item starts pending
    # and the user picks a material on the quote edit page.
    mv = await material_repo.auto_resolve_for_gcode(session, mat_type)
    q = Quote(
        kind=payload.kind,
        user_id=user.id,
        status=QuoteStatus.DRAFT,
        client_id=UUID(payload.client_id) if payload.client_id else None,
    )
    session.add(q)
    await session.flush()
    it = QuoteItem(
        quote_id=q.id,
        name=payload.name or (rec.original_path.rsplit("/", 1)[-1]),
        filename=rec.original_path,
        gcode_meta=rec.parsed_meta or {},
        material_version_id=mv.id if mv else None,
        quantity=1,
    )
    session.add(it)
    rec.status = WatcherInboxStatus.ASSIGNED
    rec.quote_id = q.id
    await session.commit()
    return {"id": str(q.id), "status": q.status}


@router.delete("/{inbox_id}", status_code=204)
async def discard(
    inbox_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    rec = await session.get(WatcherInboxFile, inbox_id)
    if not rec:
        raise HTTPException(404)
    rec.status = WatcherInboxStatus.DISCARDED
    await session.commit()
