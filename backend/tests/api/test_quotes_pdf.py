import pytest


@pytest.mark.asyncio
async def test_pdf_after_finalize(auth_client):
    await auth_client.post(
        "/materials",
        json={
            "material_code": "PLA",
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
