"""Calibration insights endpoints (W5 F1).

GET    /calibration/insights         — recomputes open insights and returns them
POST   /calibration/insights/{id}/apply    — applies the suggestion (creates a new MaterialVersion via SCD2)
POST   /calibration/insights/{id}/dismiss  — marks the insight dismissed
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.calibration import InsightApplyOut, InsightOut
from backend.core.calibration import (
    ConsumptionFact,
    InsightDraft,
    ItemFact,
    MaterialFact,
    compute_material_insights,
)
from backend.infra.db.models import (
    CalibrationInsight,
    MaterialConsumption,
    MaterialVersion,
    QuoteItem,
    User,
)
from backend.infra.db.repos import material as material_repo


router = APIRouter()


def _out(row: CalibrationInsight) -> InsightOut:
    return InsightOut(
        id=str(row.id),
        scope_kind=row.scope_kind,  # type: ignore[arg-type]
        scope_ref=row.scope_ref,
        observed_value=row.observed_value,
        current_value=row.current_value,
        suggested_value=row.suggested_value,
        delta_pct=row.delta_pct,
        sample_size=row.sample_size,
        status=row.status,  # type: ignore[arg-type]
        computed_at=row.computed_at,
    )


async def _load_facts(session: AsyncSession) -> tuple[
    list[ConsumptionFact], list[ItemFact], list[MaterialFact]
]:
    """Read everything the algorithm needs in a few cheap queries."""
    mvs = (
        await session.execute(
            select(MaterialVersion).where(MaterialVersion.is_current.is_(True))
        )
    ).scalars().all()
    mv_by_id = {mv.id: mv for mv in mvs}
    materials = [
        MaterialFact(
            material_code=mv.material_type,
            density_g_cm3=Decimal(mv.density_g_cm3),
            price_per_kg_ref=Decimal(mv.price_per_kg_ref),
            failure_rate_pct=Decimal(mv.failure_rate_pct),
        )
        for mv in mvs
    ]

    # Only items that resolved a material (pending items don't participate).
    items_rows = (
        await session.execute(
            select(QuoteItem).where(QuoteItem.material_version_id.is_not(None))
        )
    ).scalars().all()
    item_facts: list[ItemFact] = []
    for it in items_rows:
        mv = mv_by_id.get(it.material_version_id) if it.material_version_id else None
        if mv is None:
            # Historical version (not current). Skip — the catalog target is
            # always the *current* MaterialVersion, so we can't fairly
            # compare older items to it.
            continue
        filament_m = it.gcode_meta.get("filament_m") if it.gcode_meta else None
        if filament_m is None:
            continue
        item_facts.append(
            ItemFact(
                item_id=str(it.id),
                material_code=mv.material_type,
                filament_m=Decimal(str(filament_m)),
                quantity=int(it.quantity),
            )
        )

    cons_rows = (
        await session.execute(select(MaterialConsumption))
    ).scalars().all()
    consumptions = [
        ConsumptionFact(
            item_id=str(c.quote_item_id),
            grams_used=Decimal(c.grams_used),
            unit_cost_snapshot=Decimal(c.unit_cost_snapshot),
        )
        for c in cons_rows
    ]

    return consumptions, item_facts, materials


async def _delete_open_for(session: AsyncSession, drafts: list[InsightDraft]) -> None:
    """Drop open insights whose (scope_kind, scope_ref) is about to be
    recomputed. Applied/dismissed rows are preserved for audit."""
    scopes = {(d.scope_kind, d.scope_ref) for d in drafts}
    # also drop any open insights for materials whose deviation no longer
    # exceeds the threshold (so they don't linger forever).
    existing = (
        await session.execute(
            select(CalibrationInsight).where(CalibrationInsight.status == "open")
        )
    ).scalars().all()
    for row in existing:
        await session.delete(row)
    # Note: `scopes` is computed for clarity but we always wipe ALL open rows
    # — recompute is the single source of truth for the "open" window.
    del scopes


@router.get("/insights", response_model=list[InsightOut])
async def list_insights(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    consumptions, items, materials = await _load_facts(session)
    drafts = compute_material_insights(consumptions, items, materials)

    await _delete_open_for(session, drafts)
    new_rows: list[CalibrationInsight] = []
    for d in drafts:
        row = CalibrationInsight(
            scope_kind=d.scope_kind,
            scope_ref=d.scope_ref,
            observed_value=d.observed_value,
            current_value=d.current_value,
            suggested_value=d.suggested_value,
            delta_pct=d.delta_pct,
            sample_size=d.sample_size,
            status="open",
        )
        session.add(row)
        new_rows.append(row)
    await session.commit()
    for r in new_rows:
        await session.refresh(r)
    # Return open rows (newly computed + any historical that survived because
    # they were already open and matched — _delete_open_for wipes everything,
    # so this is just the new set).
    return [_out(r) for r in new_rows]


@router.post("/insights/{insight_id}/apply", response_model=InsightApplyOut)
async def apply_insight(
    insight_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    row = await session.get(CalibrationInsight, insight_id)
    if not row:
        raise HTTPException(404, "insight not found")
    if row.status != "open":
        raise HTTPException(409, f"insight already {row.status}")

    # scope_ref is material_type. When multiple current materials share the
    # same polymer family we apply the suggestion to each of them — the
    # calibration insight is aggregated at the type level.
    matches = await material_repo.current_by_type(session, row.scope_ref)
    if not matches:
        raise HTTPException(409, f"material {row.scope_ref} not found")

    previous = Decimal(matches[0].failure_rate_pct if row.scope_kind == "material_failure" else matches[0].price_per_kg_ref)
    if row.scope_kind == "material_failure":
        for mv in matches:
            await material_repo.new_version(
                session, mv.id, failure_rate_pct=row.suggested_value
            )
        field = "failure_rate_pct"
    elif row.scope_kind == "material_price":
        for mv in matches:
            await material_repo.new_version(
                session, mv.id, price_per_kg_ref=row.suggested_value
            )
        field = "price_per_kg_ref"
    else:
        raise HTTPException(400, f"unknown scope_kind {row.scope_kind}")

    row.status = "applied"
    await session.commit()

    return InsightApplyOut(
        id=str(row.id),
        status="applied",
        material_code=row.scope_ref,
        field=field,
        previous_value=previous,
        new_value=row.suggested_value,
    )


@router.post("/insights/{insight_id}/dismiss", response_model=InsightOut)
async def dismiss_insight(
    insight_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    row = await session.get(CalibrationInsight, insight_id)
    if not row:
        raise HTTPException(404, "insight not found")
    if row.status != "open":
        raise HTTPException(409, f"insight already {row.status}")
    row.status = "dismissed"
    await session.commit()
    await session.refresh(row)
    return _out(row)
