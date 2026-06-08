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
async def test_personal_workflow_skips_aprovado(auth_client):
    await _seed_material(auth_client)
    r = await auth_client.post("/quotes", json={"kind": "personal"})
    qid = r.json()["id"]
    files = {
        "file": (
            "p.gcode",
            b";TIME:60\n;Filament used:1.0m\n;Material Type:PLA\n",
            "application/octet-stream",
        )
    }
    await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "x", "quantity": "1"}
    )
    r = await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "produzido"

    r = await auth_client.post(f"/quotes/{qid}/transitions/approve")
    assert r.status_code == 400, r.text
