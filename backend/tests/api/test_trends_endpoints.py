"""Trend radar endpoint tests.

Adapters are monkeypatched so no real HTTP calls are made.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


async def _stub_google_high(term: str, *, window: str = "month"):
    return Decimal("80")


async def _stub_google_low(term: str, *, window: str = "month"):
    return Decimal("10")


async def _stub_google_none(term: str, *, window: str = "month"):
    return None


async def _stub_ml_high(term, *, creds=None, client=None):
    return (
        {
            "sold_quantity": Decimal("1500"),
            "avg_price": Decimal("90.00"),
            "top_listings": [
                {"title": "Porta celular cabeceira A", "price": 89.9, "sold": 250},
                {"title": "Porta celular cabeceira B", "price": 75.0, "sold": 120},
            ],
            "sample_size": 20,
        },
        None,
    )


async def _stub_ml_low(term, *, creds=None, client=None):
    return (
        {
            "sold_quantity": Decimal("5"),
            "avg_price": Decimal("20.00"),
            "top_listings": [],
            "sample_size": 1,
        },
        None,
    )


async def _stub_ml_empty(term, *, creds=None, client=None):
    return ({}, None)


@pytest.mark.asyncio
async def test_create_and_list_ideas(auth_client):
    r = await auth_client.post(
        "/trends/ideas", json={"term": "porta celular cabeceira"}
    )
    assert r.status_code == 201, r.text
    idea = r.json()
    assert idea["term"] == "porta celular cabeceira"

    r = await auth_client.get("/trends/ideas")
    assert r.status_code == 200
    rows = r.json()
    assert any(x["id"] == idea["id"] for x in rows)


@pytest.mark.asyncio
async def test_duplicate_term_returns_409(auth_client):
    await auth_client.post("/trends/ideas", json={"term": "suporte fone gato"})
    r = await auth_client.post("/trends/ideas", json={"term": "suporte fone gato"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_delete_idea(auth_client):
    r = await auth_client.post("/trends/ideas", json={"term": "organizador escrivaninha"})
    iid = r.json()["id"]
    r = await auth_client.delete(f"/trends/ideas/{iid}")
    assert r.status_code == 204
    r = await auth_client.get("/trends/ideas")
    assert all(x["id"] != iid for x in r.json())


async def _seed_dummy_meli_creds():
    """Ensure /trends/refresh exercises the ML branch (scheduler skips when
    creds are absent, so tests that monkeypatch fetch_volume need credentials
    present in Settings)."""
    from backend.infra.db.session import SessionFactory
    from backend.infra.db.models import Settings

    async with SessionFactory() as s:
        row = await s.get(Settings, 1)
        if row is None:
            row = Settings(id=1, meli_app_id="dummy", meli_client_secret="dummy")
            s.add(row)
        else:
            row.meli_app_id = "dummy"
            row.meli_client_secret = "dummy"
        await s.commit()


@pytest.mark.asyncio
async def test_refresh_collects_and_observations_visible(auth_client, monkeypatch):
    # Patch adapters where the scheduler uses them.
    from backend.core.trends.sources import google_trends as gt
    from backend.core.trends.sources import mercadolivre as ml

    monkeypatch.setattr(gt, "fetch_interest", _stub_google_high)
    monkeypatch.setattr(ml, "fetch_volume", _stub_ml_high)
    await _seed_dummy_meli_creds()

    r = await auth_client.post("/trends/ideas", json={"term": "luminaria led"})
    iid = r.json()["id"]

    r = await auth_client.post("/trends/refresh")
    assert r.status_code == 200, r.text
    # 1 interest + 1 sold + 1 avg_price = 3
    assert r.json()["observations_created"] == 3

    r = await auth_client.get(f"/trends/ideas/{iid}/observations")
    assert r.status_code == 200
    obs = r.json()
    sources = {(o["source"], o["metric"]) for o in obs}
    assert ("google_trends", "interest_score") in sources
    assert ("mercadolivre", "sold_quantity") in sources
    assert ("mercadolivre", "avg_price") in sources


@pytest.mark.asyncio
async def test_ranking_sorts_descending(auth_client, monkeypatch):
    from backend.core.trends.sources import google_trends as gt
    from backend.core.trends.sources import mercadolivre as ml

    # Two ideas; we'll alternate stubs by patching the function per-call.
    await auth_client.post("/trends/ideas", json={"term": "hot termo"})
    await auth_client.post("/trends/ideas", json={"term": "cold termo"})

    call_order: list[str] = []

    async def gt_dispatch(term: str, *, window: str = "month"):
        call_order.append(term)
        return Decimal("90") if term == "hot termo" else Decimal("5")

    async def ml_dispatch(term: str, *, creds=None, client=None):
        if term == "hot termo":
            return (
                {
                    "sold_quantity": Decimal("2000"),
                    "avg_price": Decimal("80"),
                    "top_listings": [{"title": "X", "price": 80.0, "sold": 200}],
                    "sample_size": 20,
                },
                None,
            )
        return (
            {
                "sold_quantity": Decimal("2"),
                "avg_price": Decimal("10"),
                "top_listings": [],
                "sample_size": 1,
            },
            None,
        )

    monkeypatch.setattr(gt, "fetch_interest", gt_dispatch)
    monkeypatch.setattr(ml, "fetch_volume", ml_dispatch)
    await _seed_dummy_meli_creds()
    # Skip the 1s sleep between ideas during tests.
    import backend.infra.scheduler.trends as sched

    async def _no_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(sched.asyncio, "sleep", _no_sleep)

    r = await auth_client.post("/trends/refresh")
    assert r.status_code == 200

    r = await auth_client.get("/trends/ranking")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 2
    assert rows[0]["term"] == "hot termo"
    assert rows[1]["term"] == "cold termo"
    assert Decimal(rows[0]["score"]) > Decimal(rows[1]["score"])
    # Top listings carried through from raw_payload of the latest ML obs.
    assert len(rows[0]["top_listings"]) >= 1


@pytest.mark.asyncio
async def test_refresh_with_failing_adapters_creates_nothing(auth_client, monkeypatch):
    from backend.core.trends.sources import google_trends as gt
    from backend.core.trends.sources import mercadolivre as ml

    monkeypatch.setattr(gt, "fetch_interest", _stub_google_none)
    monkeypatch.setattr(ml, "fetch_volume", _stub_ml_empty)

    await auth_client.post("/trends/ideas", json={"term": "vai falhar"})
    r = await auth_client.post("/trends/refresh")
    assert r.status_code == 200
    assert r.json()["observations_created"] == 0


@pytest.mark.asyncio
async def test_unauthenticated_blocked():
    from httpx import ASGITransport, AsyncClient

    from backend.app import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/trends/ideas")
        assert r.status_code == 401
