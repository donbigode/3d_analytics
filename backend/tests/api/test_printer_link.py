from decimal import Decimal

import pytest

from backend.infra.db import session as session_module
from backend.infra.db.models import PrinterJob
from backend.core.models import PrinterJobStatus
from backend.core.pricing.cost import grams_from_meters

# filament_g é persistido em JSONB como float (perde precisão além de ~15-16
# dígitos significativos frente ao Decimal de alta precisão). Compara
# arredondado a 6 casas para absorver esse ruído sem mascarar erros reais.
_Q = Decimal("0.000001")


def _q(d: Decimal) -> Decimal:
    return d.quantize(_Q)

# gcode headers with known filament lengths, all PLA (auto-resolves to the
# single registered PLA material)
_G5 = b";TIME:3600\n;Filament used:5.0m\n;Material Type:PLA\n"
_G6 = b";TIME:3600\n;Filament used:6.0m\n;Material Type:PLA\n"
_G3 = b";TIME:1800\n;Filament used:3.0m\n;Material Type:PLA\n"
_G0 = b";TIME:600\n;Filament used:0m\n;Material Type:PLA\n"
_GABS = b";TIME:600\n;Filament used:4.0m\n;Material Type:ABS\n"  # unregistered → pending


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


async def _personal_quote(auth_client):
    """Registers PLA + a 1000g spool, returns (quote_id, spool_id, density) with
    an EMPTY personal draft quote to which the caller adds items."""
    density = Decimal("1.24")
    await auth_client.post("/materials", json={
        "material_type": "PLA", "name": "PLA", "density_g_cm3": str(density),
        "price_per_kg_ref": "100", "failure_rate_pct": "0"})
    r = await auth_client.post("/spools", json={
        "material_type": "PLA", "purchased_at": "2026-01-01T00:00:00Z",
        "purchased_price": "100", "initial_grams": "1000", "remaining_grams": "1000"})
    spool_id = r.json()["id"]
    r = await auth_client.post("/quotes", json={"kind": "personal"})
    return r.json()["id"], spool_id, density


async def _add_item(auth_client, quote_id, gcode, name):
    r = await auth_client.post(
        f"/quotes/{quote_id}/items",
        files={"file": (f"{name}.gcode", gcode, "application/octet-stream")},
        data={"name": name, "quantity": "1"})
    assert r.status_code in (200, 201), r.text


@pytest.mark.asyncio
async def test_attach_binds_without_debit(auth_client):
    quote_id, spool_id, density = await _personal_quote(auth_client)
    await _add_item(auth_client, quote_id, _G5, "peca")
    jid = await _mk_job(job_uid="att1", filament_used_mm=4000)  # real 4.0m
    r = await auth_client.post(f"/printer-jobs/{jid}/link",
                               json={"quote_id": quote_id, "spool_id": spool_id})
    assert r.status_code == 200, r.text
    real = grams_from_meters(4.0, density, Decimal("1.75"))
    sp = (await auth_client.get(f"/spools/{spool_id}")).json()
    assert Decimal(str(sp["remaining_grams"])) == Decimal("1000")   # NÃO baixou
    q = (await auth_client.get(f"/quotes/{quote_id}")).json()
    assert q["status"] == "draft"                                   # status intacto
    assert _q(Decimal(str(q["items"][0]["gcode_meta"]["filament_g"]))) == _q(real)
    async with session_module.SessionFactory() as s:
        rec = await s.get(PrinterJob, jid)
        assert rec.inbox_status == PrinterJobStatus.LINKED
        assert str(rec.quote_id) == quote_id
        assert str(rec.spool_id) == spool_id


@pytest.mark.asyncio
async def test_attach_then_produce_debits_real_grams(auth_client):
    quote_id, spool_id, density = await _personal_quote(auth_client)
    await _add_item(auth_client, quote_id, _G5, "peca")
    jid = await _mk_job(job_uid="att2", filament_used_mm=4000)
    await auth_client.post(f"/printer-jobs/{jid}/link",
                           json={"quote_id": quote_id, "spool_id": spool_id})
    item_id = (await auth_client.get(f"/quotes/{quote_id}")).json()["items"][0]["id"]
    r = await auth_client.post(f"/quotes/{quote_id}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": spool_id}]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "em_producao"
    real = grams_from_meters(4.0, density, Decimal("1.75"))
    sp = (await auth_client.get(f"/spools/{spool_id}")).json()
    assert Decimal(str(sp["remaining_grams"])) == (
        Decimal("1000") - real
    ).quantize(Decimal("0.01"))


@pytest.mark.asyncio
async def test_attach_multi_item_proportional_no_debit(auth_client):
    quote_id, spool_id, density = await _personal_quote(auth_client)
    await _add_item(auth_client, quote_id, _G6, "A")
    await _add_item(auth_client, quote_id, _G3, "B")
    jid = await _mk_job(job_uid="attm", filament_used_mm=9000)
    r = await auth_client.post(f"/printer-jobs/{jid}/link",
                               json={"quote_id": quote_id, "spool_id": spool_id})
    assert r.status_code == 200, r.text
    q = (await auth_client.get(f"/quotes/{quote_id}")).json()
    items = {it["name"]: it for it in q["items"]}
    assert _q(Decimal(str(items["A"]["gcode_meta"]["filament_g"]))) == _q(grams_from_meters(6.0, density, Decimal("1.75")))
    assert _q(Decimal(str(items["B"]["gcode_meta"]["filament_g"]))) == _q(grams_from_meters(3.0, density, Decimal("1.75")))
    sp = (await auth_client.get(f"/spools/{spool_id}")).json()
    assert Decimal(str(sp["remaining_grams"])) == Decimal("1000")


@pytest.mark.asyncio
async def test_attach_equal_split_when_no_estimates(auth_client):
    quote_id, spool_id, density = await _personal_quote(auth_client)
    await _add_item(auth_client, quote_id, _G0, "A")
    await _add_item(auth_client, quote_id, _G0, "B")
    jid = await _mk_job(job_uid="atte", filament_used_mm=6000)
    r = await auth_client.post(f"/printer-jobs/{jid}/link",
                               json={"quote_id": quote_id, "spool_id": spool_id})
    assert r.status_code == 200, r.text
    q = (await auth_client.get(f"/quotes/{quote_id}")).json()
    total = sum(Decimal(str(it["gcode_meta"]["filament_g"])) for it in q["items"])
    assert _q(total) == _q(grams_from_meters(6.0, density, Decimal("1.75")))


@pytest.mark.asyncio
async def test_attach_unresolved_material_409(auth_client):
    quote_id, spool_id, _ = await _personal_quote(auth_client)
    await _add_item(auth_client, quote_id, _GABS, "abs")  # ABS unregistered -> pending
    jid = await _mk_job(job_uid="attu", filament_used_mm=4000)
    r = await auth_client.post(f"/printer-jobs/{jid}/link",
                               json={"quote_id": quote_id, "spool_id": spool_id})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_attach_no_items_409(auth_client):
    quote_id, spool_id, _ = await _personal_quote(auth_client)  # empty quote
    jid = await _mk_job(job_uid="attn", filament_used_mm=1000)
    r = await auth_client.post(f"/printer-jobs/{jid}/link",
                               json={"quote_id": quote_id, "spool_id": spool_id})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_attach_missing_job_404(auth_client):
    quote_id, spool_id, _ = await _personal_quote(auth_client)
    await _add_item(auth_client, quote_id, _G5, "peca")
    r = await auth_client.post(
        "/printer-jobs/00000000-0000-0000-0000-000000000000/link",
        json={"quote_id": quote_id, "spool_id": spool_id})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_attach_twice_blocked(auth_client):
    quote_id, spool_id, _ = await _personal_quote(auth_client)
    await _add_item(auth_client, quote_id, _G5, "peca")
    jid = await _mk_job(job_uid="att3", filament_used_mm=2000)
    r1 = await auth_client.post(f"/printer-jobs/{jid}/link",
                                json={"quote_id": quote_id, "spool_id": spool_id})
    assert r1.status_code == 200, r1.text
    r2 = await auth_client.post(f"/printer-jobs/{jid}/link",
                                json={"quote_id": quote_id, "spool_id": spool_id})
    assert r2.status_code == 409
