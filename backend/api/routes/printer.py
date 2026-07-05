from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.routes.quotes import apply_production
from backend.api.schemas.printer import PrintJobIn, PrintJobLinkIn
from backend.api.schemas.quotes import ConsumptionAssignment
from backend.core.models import PrinterJobStatus
from backend.core.pricing.cost import grams_from_meters
from backend.core.quote_service import grams_for_item
from backend.infra.db.models import MaterialVersion, PrinterJob, Quote, QuoteItem, User
from backend.settings import get_settings

_DIAMETER = Decimal("1.75")

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


@router.post("/{job_id}/link")
async def link_printer_job(
    job_id: UUID,
    payload: PrintJobLinkIn,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    job = await session.get(PrinterJob, job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.inbox_status != PrinterJobStatus.PENDING:
        raise HTTPException(409, "job not pending")
    q = await session.get(Quote, UUID(payload.quote_id))
    if not q:
        raise HTTPException(404, "quote not found")

    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == q.id))
    ).scalars().all()
    if not items:
        raise HTTPException(409, "quote has no items")

    # pesos por item = gramas estimadas (fallback: peso igual)
    weights: list[Decimal] = []
    densities: list[Decimal] = []
    for it in items:
        if it.material_version_id is None:
            raise HTTPException(409, f"item '{it.name}' has unresolved material")
        mv = await session.get(MaterialVersion, it.material_version_id)
        if not mv:
            raise HTTPException(409, f"item '{it.name}' has unresolved material")
        densities.append(mv.density_g_cm3)
        est = grams_for_item(it.gcode_meta, mv.density_g_cm3, it.quantity)
        weights.append(est if est > 0 else Decimal("0"))
    total_w = sum(weights)
    n = len(items)

    total_mm = Decimal(str(job.filament_used_mm))
    total_s = Decimal(str(job.time_s))

    assignments: list[ConsumptionAssignment] = []
    total_grams = Decimal("0")
    for idx, it in enumerate(items):
        frac = (weights[idx] / total_w) if total_w > 0 else (Decimal("1") / n)
        item_mm = total_mm * frac
        item_grams = grams_from_meters(float(item_mm) / 1000.0, densities[idx], _DIAMETER)
        total_grams += item_grams
        # persiste real (gramas + tempo) no gcode_meta p/ o analítico de variância
        meta = dict(it.gcode_meta or {})
        meta["filament_g"] = float(item_grams)
        meta["time_s"] = float(total_s * frac)
        it.gcode_meta = meta
        assignments.append(
            ConsumptionAssignment(
                quote_item_id=str(it.id),
                spool_id=payload.spool_id,
                grams=item_grams,
            )
        )

    await apply_production(session, q, assignments)
    job.inbox_status = PrinterJobStatus.LINKED
    job.quote_id = q.id
    job.grams = total_grams
    await session.commit()
    return {"quote_id": str(q.id), "grams": float(total_grams), "status": q.status}
