import pytest


@pytest.mark.asyncio
async def test_material_put_creates_new_version(auth_client):
    r = await auth_client.post("/materials", json={
        "material_code": "PLA", "name": "PLA",
        "density_g_cm3": "1.24", "price_per_kg_ref": "110", "failure_rate_pct": "5",
    })
    assert r.status_code == 201
    v1 = r.json()
    r = await auth_client.put("/materials/PLA", json={"price_per_kg_ref": "120"})
    assert r.status_code == 200
    v2 = r.json()
    assert v2["id"] != v1["id"]
    assert v2["price_per_kg_ref"] == "120.00"
    r = await auth_client.get("/materials/PLA/history")
    history = r.json()
    assert len(history) == 2
    assert sum(1 for v in history if v["is_current"]) == 1


@pytest.mark.asyncio
async def test_material_delete_only_if_unused(auth_client):
    await auth_client.post("/materials", json={
        "material_code": "ABS", "name": "ABS",
        "density_g_cm3": "1.04", "price_per_kg_ref": "120", "failure_rate_pct": "10",
    })
    r = await auth_client.delete("/materials/ABS")
    assert r.status_code == 204
