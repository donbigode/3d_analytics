import pytest


@pytest.mark.asyncio
async def test_spools_crud_and_adjust(auth_client):
    r = await auth_client.post("/spools", json={
        "material_type": "PLA",
        "purchased_from": "Acme",
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
async def test_delete_consumed_spool_returns_409(auth_client):
    """A spool already debited by a produced quote can't be hard-deleted —
    it would orphan the consumption history. Expect a friendly 409, not a 500."""
    await auth_client.post(
        "/materials",
        json={
            "material_type": "PLA",
            "name": "PLA",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "100",
            "failure_rate_pct": "0",
        },
    )
    r = await auth_client.post("/spools", json={
        "material_type": "PLA",
        "purchased_at": "2026-06-01T00:00:00Z",
        "purchased_price": "100",
        "initial_grams": "1000",
        "remaining_grams": "1000",
    })
    sid = r.json()["id"]

    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("x.gcode", b";TIME:60\n;Filament used:5.0m\n;Material Type:PLA\n",
                      "application/octet-stream")}
    await auth_client.post(f"/quotes/{qid}/items", files=files,
                           data={"name": "X", "quantity": "1"})
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    await auth_client.post(f"/quotes/{qid}/transitions/approve")
    item_id = (await auth_client.get(f"/quotes/{qid}")).json()["items"][0]["id"]
    await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]},
    )

    r = await auth_client.delete(f"/spools/{sid}")
    assert r.status_code == 409, r.text
    # still retrievable — delete was refused, not half-applied
    assert (await auth_client.get(f"/spools/{sid}")).status_code == 200


@pytest.mark.asyncio
async def test_spool_remaining_cannot_exceed_initial(auth_client):
    r = await auth_client.post("/spools", json={
        "material_type": "PLA",
        "purchased_at": "2026-06-01T00:00:00Z",
        "purchased_price": "100",
        "initial_grams": "1000",
        "remaining_grams": "1500",
    })
    assert r.status_code == 400
