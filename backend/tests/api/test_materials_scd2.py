import pytest


@pytest.mark.asyncio
async def test_material_put_creates_new_version(auth_client):
    r = await auth_client.post(
        "/materials",
        json={
            "material_type": "PLA",
            "name": "PLA Voolt Preto",
            "manufacturer": "Voolt",
            "color": "Preto",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "110",
            "failure_rate_pct": "5",
        },
    )
    assert r.status_code == 201
    v1 = r.json()
    assert v1["manufacturer"] == "Voolt"
    assert v1["color"] == "Preto"

    r = await auth_client.put(f"/materials/{v1['id']}", json={"price_per_kg_ref": "120"})
    assert r.status_code == 200
    v2 = r.json()
    assert v2["id"] != v1["id"]
    assert v2["price_per_kg_ref"] == "120.00"
    # carries over manufacturer + color
    assert v2["manufacturer"] == "Voolt"
    assert v2["color"] == "Preto"

    r = await auth_client.get(f"/materials/{v2['id']}/history")
    history = r.json()
    assert len(history) == 2
    assert sum(1 for v in history if v["is_current"]) == 1


@pytest.mark.asyncio
async def test_material_delete_only_if_unused(auth_client):
    r = await auth_client.post(
        "/materials",
        json={
            "material_type": "ABS",
            "name": "ABS",
            "density_g_cm3": "1.04",
            "price_per_kg_ref": "120",
            "failure_rate_pct": "10",
        },
    )
    mat_id = r.json()["id"]
    r = await auth_client.delete(f"/materials/{mat_id}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_multiple_materials_same_type(auth_client):
    """Two PLAs from different manufacturers are independently tracked."""
    r1 = await auth_client.post(
        "/materials",
        json={
            "material_type": "PLA",
            "name": "PLA Voolt Preto",
            "manufacturer": "Voolt",
            "color": "Preto",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "110",
            "failure_rate_pct": "5",
        },
    )
    r2 = await auth_client.post(
        "/materials",
        json={
            "material_type": "PLA",
            "name": "PLA Esun Branco",
            "manufacturer": "Esun",
            "color": "Branco",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "95",
            "failure_rate_pct": "5",
        },
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    listing = (await auth_client.get("/materials")).json()
    plas = [m for m in listing if m["material_type"] == "PLA"]
    assert len(plas) == 2
