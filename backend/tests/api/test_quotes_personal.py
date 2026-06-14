from decimal import Decimal

import pytest


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


async def _seed_spool(client, initial="1000", remaining="1000"):
    r = await client.post(
        "/spools",
        json={
            "material_type": "PLA",
            "purchased_at": "2026-06-01T00:00:00Z",
            "purchased_price": "100",
            "initial_grams": initial,
            "remaining_grams": remaining,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _personal_quote_with_item(client):
    r = await client.post("/quotes", json={"kind": "personal"})
    qid = r.json()["id"]
    files = {
        "file": (
            "p.gcode",
            b";TIME:60\n;Filament used:1.0m\n;Material Type:PLA\n",
            "application/octet-stream",
        )
    }
    await client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "x", "quantity": "1"}
    )
    item_id = (await client.get(f"/quotes/{qid}")).json()["items"][0]["id"]
    return qid, item_id


@pytest.mark.asyncio
async def test_personal_rejects_labor_service(auth_client):
    await _seed_material(auth_client)
    r = await auth_client.post(
        "/services",
        json={
            "name": "Slicing",
            "unit": "min",
            "default_rate": "1",
            "kind": "labor",
            "is_active": True,
        },
    )
    svc_id = r.json()["id"]
    r = await auth_client.post("/quotes", json={"kind": "personal"})
    qid = r.json()["id"]
    r = await auth_client.post(
        f"/quotes/{qid}/services", json={"service_id": svc_id, "quantity": "5"}
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_personal_accepts_non_labor_service(auth_client):
    await _seed_material(auth_client)
    r = await auth_client.post(
        "/services",
        json={
            "name": "Purge",
            "unit": "g",
            "default_rate": "0.5",
            "kind": "purge",
            "is_active": True,
        },
    )
    svc_id = r.json()["id"]
    r = await auth_client.post("/quotes", json={"kind": "personal"})
    qid = r.json()["id"]
    r = await auth_client.post(
        f"/quotes/{qid}/services", json={"service_id": svc_id, "quantity": "10"}
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_personal_produce_consumes_spool(auth_client):
    """Personal projects are an expense: producing one must debit the spool
    the user selected, just like commercial quotes do."""
    await _seed_material(auth_client)
    spool_id = await _seed_spool(auth_client)
    qid, item_id = await _personal_quote_with_item(auth_client)

    r = await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": spool_id}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "em_producao"  # entra na fila; material já debitado

    s = (await auth_client.get(f"/spools/{spool_id}")).json()
    assert Decimal(s["remaining_grams"]) < Decimal("1000")

    r = await auth_client.post(f"/quotes/{qid}/transitions/complete", json={"attempts": 1})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "produzido"
    assert r.json()["produced_at"] is not None


@pytest.mark.asyncio
async def test_personal_workflow_skips_aprovado(auth_client):
    await _seed_material(auth_client)
    spool_id = await _seed_spool(auth_client)
    qid, item_id = await _personal_quote_with_item(auth_client)

    r = await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": spool_id}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "em_producao"

    r = await auth_client.post(f"/quotes/{qid}/transitions/approve")
    assert r.status_code == 400, r.text
