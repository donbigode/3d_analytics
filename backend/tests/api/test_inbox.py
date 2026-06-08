import pytest

from backend.infra.db import session as session_module
from backend.infra.db.models import WatcherInboxFile
from backend.core.models import WatcherInboxStatus


@pytest.mark.asyncio
async def test_inbox_list_and_promote(auth_client):
    async with session_module.SessionFactory() as s:
        rec = WatcherInboxFile(
            file_hash="h1",
            original_path="/tmp/x.gcode",
            parsed_meta={"time_s": 60, "filament_m": 1.0, "material": "PLA", "machine": "K2"},
        )
        s.add(rec)
        await s.commit()
        await s.refresh(rec)
        inbox_id = str(rec.id)

    # need material so promotion can resolve material_version
    r_mat = await auth_client.post(
        "/materials",
        json={
            "material_type": "PLA",
            "name": "PLA",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "100",
            "failure_rate_pct": "0",
        },
    )
    assert r_mat.status_code == 201, r_mat.text

    r = await auth_client.get("/inbox")
    assert r.status_code == 200
    payload = r.json()
    assert any(i["id"] == inbox_id for i in payload)
    found = next(i for i in payload if i["id"] == inbox_id)
    assert found["parsed_meta"]["material"] == "PLA"

    r = await auth_client.post(f"/inbox/{inbox_id}/promote", json={"kind": "personal"})
    assert r.status_code == 200, r.text
    quote = r.json()
    assert "id" in quote
    assert quote["status"] in ("draft", "produzido")

    # row should now be assigned + linked to the new quote
    async with session_module.SessionFactory() as s:
        updated = await s.get(WatcherInboxFile, rec.id)
        assert updated is not None
        assert updated.status == WatcherInboxStatus.ASSIGNED
        assert str(updated.quote_id) == quote["id"]


@pytest.mark.asyncio
async def test_inbox_list_filters_non_pending(auth_client):
    async with session_module.SessionFactory() as s:
        pending = WatcherInboxFile(
            file_hash="pending1",
            original_path="/tmp/a.gcode",
            parsed_meta={"time_s": 10, "filament_m": 0.5, "material": "PLA", "machine": "K2"},
        )
        discarded = WatcherInboxFile(
            file_hash="discarded1",
            original_path="/tmp/b.gcode",
            parsed_meta={"time_s": 10, "filament_m": 0.5, "material": "PLA", "machine": "K2"},
            status=WatcherInboxStatus.DISCARDED,
        )
        s.add_all([pending, discarded])
        await s.commit()
        pending_id = str(pending.id)
        discarded_id = str(discarded.id)

    r = await auth_client.get("/inbox")
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()}
    assert pending_id in ids
    assert discarded_id not in ids


@pytest.mark.asyncio
async def test_promote_missing_returns_404(auth_client):
    # well-formed UUID that does not exist
    r = await auth_client.post(
        "/inbox/00000000-0000-0000-0000-000000000000/promote",
        json={"kind": "personal"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_promote_already_assigned_returns_404(auth_client):
    async with session_module.SessionFactory() as s:
        rec = WatcherInboxFile(
            file_hash="assigned1",
            original_path="/tmp/c.gcode",
            parsed_meta={"time_s": 10, "filament_m": 0.5, "material": "PLA", "machine": "K2"},
            status=WatcherInboxStatus.ASSIGNED,
        )
        s.add(rec)
        await s.commit()
        await s.refresh(rec)
        inbox_id = str(rec.id)

    r = await auth_client.post(f"/inbox/{inbox_id}/promote", json={"kind": "personal"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_promote_without_registered_material_creates_pending(auth_client):
    """Since the pending-material workflow, promoting an inbox row whose
    material isn't registered creates the quote anyway with the item in a
    pending state. The user resolves it later from the quote edit page."""
    async with session_module.SessionFactory() as s:
        rec = WatcherInboxFile(
            file_hash="nomat",
            original_path="/tmp/d.gcode",
            parsed_meta={"time_s": 10, "filament_m": 0.5, "material": "PETG", "machine": "K2"},
        )
        s.add(rec)
        await s.commit()
        await s.refresh(rec)
        inbox_id = str(rec.id)

    r = await auth_client.post(f"/inbox/{inbox_id}/promote", json={"kind": "personal"})
    assert r.status_code == 200, r.text
    # quote was created; the QuoteItem (added by the inbox flow) is pending
    qid = r.json()["id"]
    q = (await auth_client.get(f"/quotes/{qid}")).json()
    assert q["pending_items"] >= 1


@pytest.mark.asyncio
async def test_discard_marks_row_discarded(auth_client):
    async with session_module.SessionFactory() as s:
        rec = WatcherInboxFile(
            file_hash="disc1",
            original_path="/tmp/e.gcode",
            parsed_meta={"time_s": 10, "filament_m": 0.5, "material": "PLA", "machine": "K2"},
        )
        s.add(rec)
        await s.commit()
        await s.refresh(rec)
        inbox_id = str(rec.id)

    r = await auth_client.delete(f"/inbox/{inbox_id}")
    assert r.status_code == 204

    async with session_module.SessionFactory() as s:
        updated = await s.get(WatcherInboxFile, rec.id)
        assert updated is not None
        assert updated.status == WatcherInboxStatus.DISCARDED

    # listing should no longer show it
    r = await auth_client.get("/inbox")
    assert all(i["id"] != inbox_id for i in r.json())


@pytest.mark.asyncio
async def test_discard_missing_returns_404(auth_client):
    r = await auth_client.delete("/inbox/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_inbox_requires_auth():
    from httpx import ASGITransport, AsyncClient
    from backend.app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/inbox")
        assert r.status_code == 401
