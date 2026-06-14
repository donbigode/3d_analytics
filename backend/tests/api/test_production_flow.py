import pytest

GCODE = b";TIME:3600\n;Filament used:5.0m\n;Material Type:PLA\n"


async def _seed_material(c):
    await c.post("/materials", json={"material_type": "PLA", "name": "PLA",
        "density_g_cm3": "1.24", "price_per_kg_ref": "100", "failure_rate_pct": "0"})


async def _spool(c):
    r = await c.post("/spools", json={"material_type": "PLA",
        "purchased_at": "2026-06-01T00:00:00Z", "purchased_price": "100",
        "initial_grams": "1000", "remaining_grams": "1000"})
    return r.json()["id"]


async def _approved_commercial(c):
    r = await c.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    await c.post(f"/quotes/{qid}/items",
                 files={"file": ("x.gcode", GCODE, "application/octet-stream")},
                 data={"name": "X", "quantity": "1"})
    await c.post(f"/quotes/{qid}/transitions/finalize")
    await c.post(f"/quotes/{qid}/transitions/approve")
    item_id = (await c.get(f"/quotes/{qid}")).json()["items"][0]["id"]
    return qid, item_id


@pytest.mark.asyncio
async def test_production_event_table_exists(auth_client):
    from backend.infra.db.models import ProductionEvent
    assert ProductionEvent.__tablename__ == "production_events"
    cols = set(ProductionEvent.__table__.columns.keys())
    assert {"id", "quote_id", "kind", "outcome", "attempts",
            "failure_description", "context", "grams_wasted",
            "embedding", "llm_tags", "created_at"} <= cols
