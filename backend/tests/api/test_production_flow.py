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


async def _approved_commercial_zero_filament(c):
    """Approved commercial quote whose item has filament_m=0 (parser miss)."""
    gcode = b";TIME:3600\n;Filament used:0m\n;Material Type:PLA\n"
    r = await c.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    await c.post(f"/quotes/{qid}/items",
                 files={"file": ("z.gcode", gcode, "application/octet-stream")},
                 data={"name": "Z", "quantity": "1"})
    await c.post(f"/quotes/{qid}/transitions/finalize")
    await c.post(f"/quotes/{qid}/transitions/approve")
    item_id = (await c.get(f"/quotes/{qid}")).json()["items"][0]["id"]
    return qid, item_id


@pytest.mark.asyncio
async def test_produce_with_grams_override_debits_that_amount(auth_client):
    from decimal import Decimal
    await _seed_material(auth_client)
    sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial_zero_filament(auth_client)
    # filament_m=0 normalmente bloqueia; com override de gramas, produz.
    r = await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [
            {"quote_item_id": item_id, "spool_id": sid, "grams": "30"}
        ]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "em_producao"
    s = (await auth_client.get(f"/spools/{sid}")).json()
    assert Decimal(s["remaining_grams"]) == Decimal("970.00")  # 1000 - 30


@pytest.mark.asyncio
async def test_produce_with_filament_override_computes_and_persists(auth_client):
    from decimal import Decimal
    await _seed_material(auth_client)
    sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial_zero_filament(auth_client)
    r = await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [
            {"quote_item_id": item_id, "spool_id": sid, "filament_m": 5.0}
        ]})
    assert r.status_code == 200, r.text
    s = (await auth_client.get(f"/spools/{sid}")).json()
    assert Decimal(s["remaining_grams"]) < Decimal("1000")  # debitou o calculado
    # persistiu a metragem no item
    item = (await auth_client.get(f"/quotes/{qid}")).json()["items"][0]
    assert float(item["gcode_meta"]["filament_m"]) == 5.0


@pytest.mark.asyncio
async def test_produce_enters_em_producao(auth_client):
    from decimal import Decimal
    await _seed_material(auth_client)
    sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial(auth_client)
    r = await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "em_producao"
    s = (await auth_client.get(f"/spools/{sid}")).json()
    assert Decimal(s["remaining_grams"]) < Decimal("1000")  # material já deduzido


@pytest.mark.asyncio
async def test_complete_marks_produzido_and_logs_success(auth_client):
    await _seed_material(auth_client)
    sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    r = await auth_client.post(f"/quotes/{qid}/transitions/complete", json={"attempts": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "produzido"
    assert body["produced_at"] is not None


@pytest.mark.asyncio
async def test_fail_marks_falhou_and_logs_failure(auth_client):
    await _seed_material(auth_client)
    sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    r = await auth_client.post(f"/quotes/{qid}/transitions/fail",
        json={"failure_description": "descolou da mesa", "attempts": 3})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "falhou"
    # re-produzir: de falhou volta a em_producao (deduz de novo)
    r2 = await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "em_producao"


@pytest.mark.asyncio
async def test_production_event_table_exists(auth_client):
    from backend.infra.db.models import ProductionEvent
    assert ProductionEvent.__tablename__ == "production_events"
    cols = set(ProductionEvent.__table__.columns.keys())
    assert {"id", "quote_id", "kind", "outcome", "attempts",
            "failure_description", "context", "grams_wasted",
            "embedding", "llm_tags", "created_at"} <= cols
