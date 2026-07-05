from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session
from backend.api.schemas.printer import PrintJobIn
from backend.core.models import PrinterJobStatus
from backend.infra.db.models import PrinterJob
from backend.settings import get_settings

ingest_router = APIRouter()

_ALLOWED_STATUS = {"completed", "cancelled", "error"}


def _require_agent(request: Request) -> None:
    token = get_settings().agent_ingest_token
    if not token:
        raise HTTPException(503, "ingest not configured")
    header = request.headers.get("authorization", "")
    if header != f"Bearer {token}":
        raise HTTPException(401, "invalid agent token")


@ingest_router.post("/print-jobs", status_code=201)
async def ingest_print_job(
    payload: PrintJobIn,
    request: Request,
    session: AsyncSession = Depends(db_session),
):
    _require_agent(request)
    if payload.status not in _ALLOWED_STATUS:
        raise HTTPException(422, f"unknown status '{payload.status}'")

    existing = await session.scalar(
        select(PrinterJob).where(
            PrinterJob.machine == payload.machine,
            PrinterJob.job_uid == payload.job_uid,
        )
    )
    if existing:
        # Idempotente: nunca sobrescreve; devolve o registro já conhecido.
        return {"id": str(existing.id), "inbox_status": existing.inbox_status}

    job = PrinterJob(
        machine=payload.machine,
        job_uid=payload.job_uid,
        filename=payload.filename,
        status=payload.status,
        filament_used_mm=payload.filament_used_mm,
        time_s=payload.print_duration_s,
        started_at=payload.started_at,
        finished_at=payload.finished_at,
        raw=payload.raw,
        inbox_status=PrinterJobStatus.PENDING,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return {"id": str(job.id), "inbox_status": job.inbox_status}
