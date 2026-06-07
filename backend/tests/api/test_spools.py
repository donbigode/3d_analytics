import pytest


@pytest.mark.asyncio
async def test_spools_crud_and_adjust(auth_client):
    r = await auth_client.post("/spools", json={
        "material_code": "PLA",
        "supplier": "Acme",
        "batch_code": "B1",
        "purchased_at": "2026-06-01T00:00:00Z",
        "purchased_price": "100",
        "initial_grams": "1000",
        "remaining_grams": "1000",
    })
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = await auth_client.get("/spools")
    assert any(s["id"] == sid for s in r.json())

    r = await auth_client.get(f"/spools/{sid}")
    assert r.status_code == 200

    r = await auth_client.put(f"/spools/{sid}", json={"remaining_grams": "500"})
    assert r.status_code == 200
    assert r.json()["remaining_grams"] == "500.00"

    r = await auth_client.delete(f"/spools/{sid}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_spool_remaining_cannot_exceed_initial(auth_client):
    r = await auth_client.post("/spools", json={
        "material_code": "PLA",
        "purchased_at": "2026-06-01T00:00:00Z",
        "purchased_price": "100",
        "initial_grams": "1000",
        "remaining_grams": "1500",
    })
    assert r.status_code == 400
