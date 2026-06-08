"""Wikipedia pageviews adapter with mocked HTTP."""
from decimal import Decimal

import httpx
import pytest

from backend.core.trends.sources.wikipedia import _normalize_title, fetch_interest


def test_normalize_title_capitalizes():
    assert _normalize_title("impressão 3d") == "Impressão_3d"
    assert _normalize_title("Coelho") == "Coelho"
    assert _normalize_title("  espaços  ") == "Espaços"


@pytest.mark.asyncio
async def test_fetch_interest_returns_mean_views():
    def handler(request: httpx.Request) -> httpx.Response:
        # API returns one item per day; we mock 3 days of data.
        return httpx.Response(
            200,
            json={
                "items": [
                    {"views": 100, "timestamp": "2026060100"},
                    {"views": 200, "timestamp": "2026060200"},
                    {"views": 300, "timestamp": "2026060300"},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        v = await fetch_interest("Impressão 3D", window="week", client=client)
    assert v == Decimal("200.00")


@pytest.mark.asyncio
async def test_fetch_interest_404_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"type": "https://...", "title": "Not Found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        v = await fetch_interest("artigo_inexistente_xyz", client=client)
    assert v is None


@pytest.mark.asyncio
async def test_fetch_interest_empty_items_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"items": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        v = await fetch_interest("termo", client=client)
    assert v is None
