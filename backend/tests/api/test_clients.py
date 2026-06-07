import pytest


@pytest.mark.asyncio
async def test_clients_crud(auth_client):
    r = await auth_client.post("/clients", json={"name": "Ana", "phone": "+55"})
    assert r.status_code == 201
    cid = r.json()["id"]
    r = await auth_client.get("/clients")
    assert any(c["id"] == cid for c in r.json())
    r = await auth_client.put(f"/clients/{cid}", json={"name": "Ana K"})
    assert r.json()["name"] == "Ana K"
    r = await auth_client.delete(f"/clients/{cid}")
    assert r.status_code == 204
