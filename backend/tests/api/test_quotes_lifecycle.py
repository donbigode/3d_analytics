import pytest
from decimal import Decimal


GCODE_SAMPLE = b";TIME:3600\n;Filament used:5.0m\n;Material Type:PLA\n;Machine Name:K2\n"


async def _seed_material(client):
    await client.post(
        "/materials",
        json={
            "material_code": "PLA",
            "name": "PLA",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "100",
            "failure_rate_pct": "0",
        },
    )


@pytest.mark.asyncio
async def test_commercial_lifecycle(auth_client):
    await _seed_material(auth_client)

    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    assert r.status_code == 201, r.text
    qid = r.json()["id"]
    assert r.json()["status"] == "draft"

    files = {"file": ("test.gcode", GCODE_SAMPLE, "application/octet-stream")}
    r = await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "Peca A", "quantity": "1"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Peca A"

    r = await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "orcado"
    assert r.json()["finalized_at"] is not None

    r = await auth_client.post(f"/quotes/{qid}/transitions/approve")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "aprovado"


@pytest.mark.asyncio
async def test_produce_consumes_spool(auth_client):
    await _seed_material(auth_client)

    r = await auth_client.post(
        "/spools",
        json={
            "material_code": "PLA",
            "purchased_at": "2026-06-01T00:00:00Z",
            "purchased_price": "100",
            "initial_grams": "1000",
            "remaining_grams": "1000",
        },
    )
    assert r.status_code == 201, r.text
    spool_id = r.json()["id"]

    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("x.gcode", GCODE_SAMPLE, "application/octet-stream")}
    await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "X", "quantity": "1"}
    )
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    await auth_client.post(f"/quotes/{qid}/transitions/approve")

    quote = (await auth_client.get(f"/quotes/{qid}")).json()
    item_id = quote["items"][0]["id"]

    r = await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": spool_id}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "produzido"

    s = (await auth_client.get(f"/spools/{spool_id}")).json()
    assert Decimal(s["remaining_grams"]) < Decimal("1000")


@pytest.mark.asyncio
async def test_produce_insufficient_spool_returns_409(auth_client):
    await _seed_material(auth_client)
    r = await auth_client.post(
        "/spools",
        json={
            "material_code": "PLA",
            "purchased_at": "2026-06-01T00:00:00Z",
            "purchased_price": "100",
            "initial_grams": "1",
            "remaining_grams": "1",
        },
    )
    spool_id = r.json()["id"]

    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("x.gcode", GCODE_SAMPLE, "application/octet-stream")}
    await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "X", "quantity": "1"}
    )
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    await auth_client.post(f"/quotes/{qid}/transitions/approve")
    quote = (await auth_client.get(f"/quotes/{qid}")).json()
    item_id = quote["items"][0]["id"]

    r = await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": spool_id}]},
    )
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_commercial_can_deliver_after_produce(auth_client):
    await _seed_material(auth_client)
    r = await auth_client.post(
        "/spools",
        json={
            "material_code": "PLA",
            "purchased_at": "2026-06-01T00:00:00Z",
            "purchased_price": "100",
            "initial_grams": "1000",
            "remaining_grams": "1000",
        },
    )
    spool_id = r.json()["id"]
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("x.gcode", GCODE_SAMPLE, "application/octet-stream")}
    await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "X", "quantity": "1"}
    )
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    await auth_client.post(f"/quotes/{qid}/transitions/approve")
    quote = (await auth_client.get(f"/quotes/{qid}")).json()
    item_id = quote["items"][0]["id"]
    await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": spool_id}]},
    )
    r = await auth_client.post(f"/quotes/{qid}/transitions/deliver")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "entregue"


@pytest.mark.asyncio
async def test_upload_unknown_material_creates_pending_item(auth_client):
    # No material seeded — item is accepted as pending; finalize is blocked
    # until material is registered and item resolved.
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("x.gcode", GCODE_SAMPLE, "application/octet-stream")}
    r = await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "X", "quantity": "1"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["pending_items"] == 1
    item = body["items"][0]
    assert item["material_pending"] is True
    assert item["pending_material_code"] == "PLA"
    # finalize must be blocked
    r = await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    assert r.status_code == 409
    # register material and resolve item
    await auth_client.post(
        "/materials",
        json={
            "material_code": "PLA",
            "name": "PLA",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "100",
            "failure_rate_pct": "0",
        },
    )
    item_id = item["id"]
    r = await auth_client.put(
        f"/quotes/{qid}/items/{item_id}", json={"material_code": "PLA"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["material_pending"] is False
    assert r.json()["pending_items"] == 0
    # now finalize succeeds
    r = await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "orcado"
