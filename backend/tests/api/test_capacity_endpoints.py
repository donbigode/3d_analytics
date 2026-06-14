"""End-to-end tests for the capacity forecast endpoints."""

import pytest


GCODE_SAMPLE = b";TIME:3600\n;Filament used:5.0m\n;Material Type:PLA\n;Machine Name:K2\n"


async def _seed_material(client):
    await client.post(
        "/materials",
        json={
            "material_type": "PLA",
            "name": "PLA",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "100",
            "failure_rate_pct": "0",
        },
    )


async def _approved_quote(client, qty: int = 1) -> str:
    """Create + finalize + approve a commercial quote with one item (1h gcode)."""
    r = await client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("x.gcode", GCODE_SAMPLE, "application/octet-stream")}
    await client.post(
        f"/quotes/{qid}/items",
        files=files,
        data={"name": "Peca", "quantity": str(qty)},
    )
    await client.post(f"/quotes/{qid}/transitions/finalize")
    await client.post(f"/quotes/{qid}/transitions/approve")
    return qid


@pytest.mark.asyncio
async def test_forecast_empty_queue(auth_client):
    r = await auth_client.get("/capacity/forecast")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["queue_jobs"] == 0
    assert float(body["queue_hours"]) == 0.0
    assert body["days_until_clear"] == 0
    assert body["jobs"] == []
    # default hours_per_day is 22
    assert int(float(body["hours_per_day"])) == 22


@pytest.mark.asyncio
async def test_forecast_includes_approved_quotes_in_fifo(auth_client):
    await _seed_material(auth_client)
    q1 = await _approved_quote(auth_client, qty=1)
    q2 = await _approved_quote(auth_client, qty=2)

    r = await auth_client.get("/capacity/forecast")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["queue_jobs"] == 2
    # q1 was approved first → must come first in jobs[]
    assert body["jobs"][0]["quote_id"] == q1
    assert body["jobs"][1]["quote_id"] == q2
    # 1h + 2h = 3h total
    assert float(body["queue_hours"]) == pytest.approx(3.0, abs=0.01)


@pytest.mark.asyncio
async def test_forecast_respects_printer_hours_per_day(auth_client):
    await _seed_material(auth_client)
    # 5 jobs × 1h × qty 5 = 25h; with hpd=10 → ceil(25/10)=3 days
    for _ in range(5):
        await _approved_quote(auth_client, qty=5)
    await auth_client.put("/settings", json={"printer_hours_per_day": 10})

    r = await auth_client.get("/capacity/forecast")
    assert r.status_code == 200, r.text
    body = r.json()
    assert int(float(body["hours_per_day"])) == 10
    assert body["queue_jobs"] == 5
    assert float(body["queue_hours"]) == pytest.approx(25.0, abs=0.01)
    assert body["days_until_clear"] == 3


@pytest.mark.asyncio
async def test_forecast_quote_eta_in_queue(auth_client):
    await _seed_material(auth_client)
    q1 = await _approved_quote(auth_client)
    q2 = await _approved_quote(auth_client)
    q3 = await _approved_quote(auth_client)

    r = await auth_client.get(f"/capacity/forecast/quotes/{q2}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["quote_id"] == q2
    assert body["in_queue"] is True
    assert body["position"] == 2
    assert body["eta"] is not None

    # q3 must have a later ETA than q2
    r3 = await auth_client.get(f"/capacity/forecast/quotes/{q3}")
    assert r3.json()["position"] == 3
    assert r3.json()["eta"] > body["eta"]


@pytest.mark.asyncio
async def test_forecast_quote_eta_not_in_queue(auth_client):
    await _seed_material(auth_client)
    # Quote in draft → not approved → not in the queue
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    r = await auth_client.get(f"/capacity/forecast/quotes/{qid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["in_queue"] is False
    assert body["position"] is None
    assert body["eta"] is None
    # but next_available_at is still reported (it's "now" when queue empty)
    assert body["next_available_at"] is not None


@pytest.mark.asyncio
async def test_settings_includes_printer_hours_per_day(auth_client):
    r = await auth_client.get("/settings")
    assert r.status_code == 200, r.text
    assert r.json()["printer_hours_per_day"] == 22

    r = await auth_client.put("/settings", json={"printer_hours_per_day": 16})
    assert r.status_code == 200, r.text
    assert r.json()["printer_hours_per_day"] == 16


@pytest.mark.asyncio
async def test_in_production_queue_lists_em_producao(auth_client):
    await _seed_material(auth_client)
    r = await auth_client.post(
        "/spools",
        json={
            "material_type": "PLA",
            "purchased_at": "2026-06-01T00:00:00Z",
            "purchased_price": "100",
            "initial_grams": "1000",
            "remaining_grams": "1000",
        },
    )
    sid = r.json()["id"]
    qid = await _approved_quote(auth_client)
    item_id = (await auth_client.get(f"/quotes/{qid}")).json()["items"][0]["id"]
    await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]},
    )

    r = await auth_client.get("/capacity/in-production")
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    assert any(j["quote_id"] == qid for j in jobs)
