"""End-to-end tests for the calibration insights endpoints."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.core.calibration.algo import _grams_per_meter
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    CalibrationInsight,
    MaterialConsumption,
    MaterialVersion,
    Quote,
    QuoteItem,
    Spool,
    User,
)


async def _seed_material_failure_scenario(user_id):
    """Insert PLA + 6 quote items + 6 consumptions with ~15% extra waste."""
    async with session_module.SessionFactory() as s:
        mv = MaterialVersion(
            material_code="PLA",
            name="PLA",
            density_g_cm3=Decimal("1.24"),
            price_per_kg_ref=Decimal("100"),
            failure_rate_pct=Decimal("0"),
            is_current=True,
        )
        s.add(mv)
        spool = Spool(
            material_code="PLA",
            supplier=None,
            batch_code=None,
            purchased_at=datetime.now(timezone.utc),
            purchased_price=Decimal("100"),
            initial_grams=Decimal("1000"),
            remaining_grams=Decimal("1000"),
            status="open",
        )
        s.add(spool)
        await s.flush()

        q = Quote(
            kind="commercial",
            user_id=user_id,
            status="produzido",
            markup_pct=Decimal("0"),
            min_charge=Decimal("0"),
            client_id=None,
        )
        s.add(q)
        await s.flush()

        theoretical = _grams_per_meter(Decimal("1.24")) * Decimal("5")  # grams per item
        real = theoretical * Decimal("1.15")  # 15% extra waste

        for i in range(6):
            it = QuoteItem(
                quote_id=q.id,
                name=f"P{i}",
                filename=f"p{i}.gcode",
                gcode_meta={"filament_m": 5.0, "time_s": 3600, "material": "PLA"},
                material_version_id=mv.id,
                quantity=1,
            )
            s.add(it)
            await s.flush()
            s.add(
                MaterialConsumption(
                    quote_item_id=it.id,
                    spool_id=spool.id,
                    grams_used=real,
                    unit_cost_snapshot=Decimal("0.10"),  # matches catalog
                )
            )
        await s.commit()
        return mv.id


async def _get_user_id() -> "uuid":
    async with session_module.SessionFactory() as s:
        from sqlalchemy import select
        res = await s.execute(select(User))
        return res.scalars().first().id


@pytest.mark.asyncio
async def test_get_insights_empty_when_no_data(auth_client):
    r = await auth_client.get("/calibration/insights")
    assert r.status_code == 200, r.text
    assert r.json() == []


@pytest.mark.asyncio
async def test_get_insights_surfaces_failure_rate(auth_client):
    user_id = await _get_user_id()
    await _seed_material_failure_scenario(user_id)

    r = await auth_client.get("/calibration/insights")
    assert r.status_code == 200, r.text
    body = r.json()
    failures = [d for d in body if d["scope_kind"] == "material_failure"]
    assert len(failures) == 1
    f = failures[0]
    assert f["scope_ref"] == "PLA"
    assert f["sample_size"] == 6
    assert f["status"] == "open"
    # observed ≈ 15%, current 0% — Pydantic returns Decimal as string
    assert abs(Decimal(f["observed_value"]) - Decimal("15.00")) < Decimal("0.1")
    assert Decimal(f["current_value"]) == Decimal("0.00")


@pytest.mark.asyncio
async def test_apply_creates_new_material_version(auth_client):
    user_id = await _get_user_id()
    await _seed_material_failure_scenario(user_id)

    r = await auth_client.get("/calibration/insights")
    insights = [d for d in r.json() if d["scope_kind"] == "material_failure"]
    assert insights, r.text
    insight_id = insights[0]["id"]
    suggested = insights[0]["suggested_value"]

    r = await auth_client.post(f"/calibration/insights/{insight_id}/apply")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "applied"
    assert body["material_code"] == "PLA"
    assert body["field"] == "failure_rate_pct"
    assert Decimal(body["previous_value"]) == Decimal("0")
    assert Decimal(body["new_value"]) == Decimal(suggested)

    # verify a new SCD2 version exists
    r = await auth_client.get("/materials/PLA/history")
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 2
    current = [v for v in history if v["is_current"]][0]
    assert Decimal(current["failure_rate_pct"]) == Decimal(suggested)

    # re-applying the same insight should 409
    r = await auth_client.post(f"/calibration/insights/{insight_id}/apply")
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_dismiss_marks_dismissed(auth_client):
    user_id = await _get_user_id()
    await _seed_material_failure_scenario(user_id)

    r = await auth_client.get("/calibration/insights")
    insight_id = [d for d in r.json() if d["scope_kind"] == "material_failure"][0]["id"]

    r = await auth_client.post(f"/calibration/insights/{insight_id}/dismiss")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "dismissed"

    # cannot dismiss again
    r = await auth_client.post(f"/calibration/insights/{insight_id}/dismiss")
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_recompute_drops_previous_open_rows(auth_client):
    user_id = await _get_user_id()
    await _seed_material_failure_scenario(user_id)

    r = await auth_client.get("/calibration/insights")
    first = r.json()
    assert len(first) >= 1

    # second call: same scenario → same set, but old open rows are wiped & rebuilt.
    r = await auth_client.get("/calibration/insights")
    second = r.json()
    assert len(second) == len(first)
    # IDs are fresh — the old open rows got dropped and recreated.
    assert {d["id"] for d in first}.isdisjoint({d["id"] for d in second})


@pytest.mark.asyncio
async def test_endpoints_require_auth(client):
    r = await client.get("/calibration/insights")
    assert r.status_code == 401
    fake = str(uuid4())
    r = await client.post(f"/calibration/insights/{fake}/apply")
    assert r.status_code == 401
    r = await client.post(f"/calibration/insights/{fake}/dismiss")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_apply_unknown_insight_returns_404(auth_client):
    fake = str(uuid4())
    r = await auth_client.post(f"/calibration/insights/{fake}/apply")
    assert r.status_code == 404
