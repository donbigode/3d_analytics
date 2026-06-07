import pytest


@pytest.mark.asyncio
async def test_services_crud(auth_client):
    r = await auth_client.post("/services", json={
        "name": "Modelagem", "unit": "hour", "default_rate": "80", "kind": "labor",
    })
    assert r.status_code == 201
    sid = r.json()["id"]

    r = await auth_client.get("/services")
    assert any(s["id"] == sid for s in r.json())

    r = await auth_client.get(f"/services/{sid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Modelagem"

    r = await auth_client.put(f"/services/{sid}", json={"default_rate": "90"})
    assert r.status_code == 200
    assert r.json()["default_rate"] == "90.00"

    r = await auth_client.delete(f"/services/{sid}")
    assert r.status_code == 204
