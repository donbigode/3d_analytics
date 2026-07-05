from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.printer import PrintJobIn
from backend.core.models import PrinterJobStatus
from backend.infra.db.models import PrinterJob, User
from backend.settings import get_settings

ingest_router = APIRouter()
router = APIRouter()

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
    response: Response,
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
        response.status_code = 200
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
    try:
        await session.commit()
    except IntegrityError:
        # Corrida perdida contra uq_printer_jobs_machine_job: outro insert
        # concorrente venceu. Recupera o registro já existente e devolve
        # como idempotente, em vez de propagar 500.
        await session.rollback()
        existing = await session.scalar(
            select(PrinterJob).where(
                PrinterJob.machine == payload.machine,
                PrinterJob.job_uid == payload.job_uid,
            )
        )
        response.status_code = 200
        return {"id": str(existing.id), "inbox_status": existing.inbox_status}
    await session.refresh(job)
    return {"id": str(job.id), "inbox_status": job.inbox_status}


@router.get("")
async def list_printer_jobs(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    rows = (
        await session.execute(
            select(PrinterJob)
            .where(PrinterJob.inbox_status == PrinterJobStatus.PENDING)
            .order_by(PrinterJob.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "machine": r.machine,
            "filename": r.filename,
            "status": r.status,
            "filament_used_mm": float(r.filament_used_mm),
            "time_s": float(r.time_s),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.delete("/{job_id}", status_code=204)
async def discard_printer_job(
    job_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    rec = await session.get(PrinterJob, job_id)
    if not rec:
        raise HTTPException(404)
    rec.inbox_status = PrinterJobStatus.DISCARDED
    await session.commit()
