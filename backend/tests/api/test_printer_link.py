from decimal import Decimal

import pytest

from backend.infra.db import session as session_module
from backend.infra.db.models import PrinterJob
from backend.core.models import PrinterJobStatus
from backend.core.pricing.cost import grams_from_meters

# gcode header parsed on upload: filament_m=5.0, material PLA (auto-resolves
# to the single registered PLA material, so the item gets a material_version_id)
_GCODE = b";TIME:3600\n;Filament used:5.0m\n;Material Type:PLA\n"


async def _setup_personal_quote_one_item(auth_client):
    """Personal quote in DRAFT with one resolved-material item. Returns
    (quote_id, spool_id, density). Draft + resolved material = produce-eligible."""
    density = Decimal("1.24")
    r = await auth_client.post("/materials", json={
        "material_type": "PLA", "name": "PLA", "density_g_cm3": str(density),
        "price_per_kg_ref": "100", "failure_rate_pct": "0"})
    assert r.status_code == 201, r.text
    r = await auth_client.post("/spools", json={
        "material_type": "PLA", "purchased_at": "2026-01-01T00:00:00Z",
        "purchased_price": "100", "initial_grams": "1000", "remaining_grams": "1000"})
    assert r.status_code == 201, r.text
    spool_id = r.json()["id"]
    r = await auth_client.post("/quotes", json={"kind": "personal"})
    quote_id = r.json()["id"]
    r = await auth_client.post(
        f"/quotes/{quote_id}/items",
        files={"file": ("p.gcode", _GCODE, "application/octet-stream")},
        data={"name": "peca", "quantity": "1"})
    assert r.status_code in (200, 201), r.text
    return quote_id, spool_id, density


async def _mk_job(**over) -> str:
    async with session_module.SessionFactory() as s:
        job = PrinterJob(
            machine="K1", job_uid=over.pop("job_uid", "1"),
            filename="p.gcode", status="completed",
            filament_used_mm=over.pop("filament_used_mm", 3000),
            time_s=5000, raw={},
            inbox_status=over.pop("inbox_status", PrinterJobStatus.PENDING),
        )
        for k, v in over.items():
            setattr(job, k, v)
        s.add(job)
        await s.commit()
        await s.refresh(job)
        return str(job.id)


@pytest.mark.asyncio
async def test_list_shows_only_pending(auth_client):
    pend = await _mk_job(job_uid="p1")
    disc = await _mk_job(job_uid="d1", inbox_status=PrinterJobStatus.DISCARDED)
    r = await auth_client.get("/printer-jobs")
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()}
    assert pend in ids
    assert disc not in ids


@pytest.mark.asyncio
async def test_discard_marks_discarded(auth_client):
    jid = await _mk_job(job_uid="x1")
    r = await auth_client.delete(f"/printer-jobs/{jid}")
    assert r.status_code == 204
    async with session_module.SessionFactory() as s:
        rec = await s.get(PrinterJob, jid)
        assert rec.inbox_status == PrinterJobStatus.DISCARDED


@pytest.mark.asyncio
async def test_link_produces_with_real_grams(auth_client):
    quote_id, spool_id, density = await _setup_personal_quote_one_item(auth_client)
    jid = await _mk_job(job_uid="link1", filament_used_mm=4000)
    r = await auth_client.post(f"/printer-jobs/{jid}/link",
                               json={"quote_id": quote_id, "spool_id": spool_id})
    assert r.status_code == 200, r.text
    expected = grams_from_meters(4.0, density, Decimal("1.75"))  # 4000mm = 4.0m
    sp = (await auth_client.get(f"/spools/{spool_id}")).json()
    # remaining_grams é Numeric(10,2) no banco: compara arredondado à mesma escala.
    assert Decimal(str(sp["remaining_grams"])) == (
        Decimal("1000") - expected
    ).quantize(Decimal("0.01"))
    q = (await auth_client.get(f"/quotes/{quote_id}")).json()
    assert q["status"] == "em_producao"
    async with session_module.SessionFactory() as s:
        rec = await s.get(PrinterJob, jid)
        assert rec.inbox_status == PrinterJobStatus.LINKED
        assert str(rec.quote_id) == quote_id


@pytest.mark.asyncio
async def test_link_twice_is_blocked(auth_client):
    quote_id, spool_id, _ = await _setup_personal_quote_one_item(auth_client)
    jid = await _mk_job(job_uid="link2", filament_used_mm=2000)
    r1 = await auth_client.post(f"/printer-jobs/{jid}/link",
                                json={"quote_id": quote_id, "spool_id": spool_id})
    assert r1.status_code == 200, r1.text
    r2 = await auth_client.post(f"/printer-jobs/{jid}/link",
                                json={"quote_id": quote_id, "spool_id": spool_id})
    assert r2.status_code == 409
