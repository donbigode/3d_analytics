import pytest


@pytest.mark.asyncio
async def test_users_list_requires_auth(auth_client):
    r = await auth_client.get("/users")
    assert r.status_code == 200
    assert any(u["email"] == "t@t.com" for u in r.json())


@pytest.mark.asyncio
async def test_users_create_and_delete(auth_client):
    r = await auth_client.post("/users", json={
        "name": "new", "email": "new@x.com", "password": "pw"
    })
    assert r.status_code == 201
    uid = r.json()["id"]
    r = await auth_client.delete(f"/users/{uid}")
    assert r.status_code == 204
