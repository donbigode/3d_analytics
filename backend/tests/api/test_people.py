import pytest


@pytest.mark.asyncio
async def test_people_crud(auth_client):
    r = await auth_client.post("/people", json={"name": "Otávio"})
    assert r.status_code == 201, r.text
    otavio = r.json()
    assert otavio["name"] == "Otávio" and otavio["active"] is True

    await auth_client.post("/people", json={"name": "Ana"})

    # nome duplicado -> 409
    dup = await auth_client.post("/people", json={"name": "Otávio"})
    assert dup.status_code == 409

    lst = (await auth_client.get("/people")).json()
    assert {p["name"] for p in lst} == {"Otávio", "Ana"}

    # inativa
    upd = await auth_client.put(f"/people/{otavio['id']}", json={"active": False})
    assert upd.status_code == 200 and upd.json()["active"] is False

    # apaga
    d = await auth_client.delete(f"/people/{otavio['id']}")
    assert d.status_code == 204
    lst2 = (await auth_client.get("/people")).json()
    assert {p["name"] for p in lst2} == {"Ana"}
