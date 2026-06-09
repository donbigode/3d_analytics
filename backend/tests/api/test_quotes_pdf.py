import pytest


async def _seed_pla(client):
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
async def test_retail_mode_toggle_persists_after_finalize(auth_client):
    """Retail mode is a presentation flag — must be flippable even after
    the quote leaves draft, since the owner may decide post-fact which
    layout to send the customer."""
    await _seed_pla(auth_client)
    r = await auth_client.post("/quotes", json={"kind": "commercial", "markup_pct": "50"})
    qid = r.json()["id"]
    assert r.json()["retail_mode"] is False
    files = {
        "file": ("p.gcode", b";TIME:3600\n;Filament used:5.0m\n;Material Type:PLA\n",
                 "application/octet-stream"),
    }
    await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "porta-caneta", "quantity": "3"}
    )
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    # Financial fields are locked after finalize, but retail_mode isn't.
    r = await auth_client.put(f"/quotes/{qid}", json={"markup_pct": "70"})
    assert r.status_code == 409
    r = await auth_client.put(f"/quotes/{qid}", json={"retail_mode": True})
    assert r.status_code == 200, r.text
    assert r.json()["retail_mode"] is True
    r = await auth_client.get(f"/quotes/{qid}/pdf")
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_pdf_after_finalize(auth_client):
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
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {
        "file": (
            "p.gcode",
            b";TIME:3600\n;Filament used:5.0m\n;Material Type:PLA\n",
            "application/octet-stream",
        )
    }
    await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "x", "quantity": "1"}
    )
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    r = await auth_client.get(f"/quotes/{qid}/pdf")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
