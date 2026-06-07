"""Mercado Livre adapter with mocked OAuth + search."""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend.core.trends.sources.mercadolivre import (
    MeliCredentials,
    _is_token_valid,
    fetch_volume,
)


def test_is_token_valid_true_when_future():
    creds = MeliCredentials(
        app_id="x",
        client_secret="y",
        access_token="t",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert _is_token_valid(creds) is True


def test_is_token_valid_false_when_past():
    creds = MeliCredentials(
        app_id="x",
        client_secret="y",
        access_token="t",
        token_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    assert _is_token_valid(creds) is False


def test_is_token_valid_false_when_missing():
    creds = MeliCredentials(app_id="x", client_secret="y")
    assert _is_token_valid(creds) is False


@pytest.mark.asyncio
async def test_fetch_volume_returns_empty_without_creds():
    stats, tu = await fetch_volume("porta celular", creds=None)
    assert stats == {}
    assert tu is None


@pytest.mark.asyncio
async def test_fetch_volume_with_oauth_flow_and_search():
    # Mock both OAuth token endpoint and search endpoint.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "minted-token",
                    "expires_in": 21600,
                    "token_type": "Bearer",
                },
            )
        if request.url.path.endswith("/search"):
            assert request.headers["authorization"] == "Bearer minted-token"
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "title": "Porta celular gato",
                            "price": 19.90,
                            "sold_quantity": 250,
                            "permalink": "https://produto/abc",
                        },
                        {
                            "title": "Porta celular cabeceira",
                            "price": 25.00,
                            "sold_quantity": 80,
                            "permalink": "https://produto/def",
                        },
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        creds = MeliCredentials(app_id="app", client_secret="sec")
        stats, tu = await fetch_volume("porta celular", creds=creds, client=client)
    assert stats["sold_quantity"] == 330
    assert float(stats["avg_price"]) == 22.45
    assert len(stats["top_listings"]) == 2
    assert tu is not None
    assert tu.access_token == "minted-token"


@pytest.mark.asyncio
async def test_fetch_volume_skips_oauth_when_token_still_valid():
    calls = {"token": 0, "search": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": "x", "expires_in": 21600})
        if request.url.path.endswith("/search"):
            calls["search"] += 1
            return httpx.Response(200, json={"results": []})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        creds = MeliCredentials(
            app_id="app",
            client_secret="sec",
            access_token="still-good",
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        stats, tu = await fetch_volume("x", creds=creds, client=client)
    assert calls["token"] == 0
    assert calls["search"] == 1
    assert tu is None  # no refresh happened
