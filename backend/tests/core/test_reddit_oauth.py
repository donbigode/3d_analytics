"""Reddit OAuth adapter with mocked HTTP."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from backend.core.trends.sources.reddit import (
    RedditCredentials,
    _is_token_valid,
    fetch_engagement,
)


def test_is_token_valid_true_when_future():
    creds = RedditCredentials(
        client_id="x",
        client_secret="y",
        access_token="t",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert _is_token_valid(creds) is True


def test_is_token_valid_false_when_past():
    creds = RedditCredentials(
        client_id="x",
        client_secret="y",
        access_token="t",
        token_expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    assert _is_token_valid(creds) is False


@pytest.mark.asyncio
async def test_fetch_engagement_returns_empty_without_creds():
    stats, tu = await fetch_engagement("porta celular", creds=None)
    assert stats == {}
    assert tu is None


@pytest.mark.asyncio
async def test_fetch_engagement_oauth_flow_then_search():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/access_token":
            # Basic auth header must be present
            assert "authorization" in request.headers
            return httpx.Response(
                200,
                json={
                    "access_token": "rd-token",
                    "expires_in": 3600,
                    "token_type": "bearer",
                },
            )
        if request.url.path == "/search":
            assert request.headers["authorization"] == "Bearer rd-token"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "children": [
                            {
                                "data": {
                                    "title": "Best 3D printed phone holder",
                                    "subreddit": "3Dprinting",
                                    "score": 1200,
                                    "num_comments": 80,
                                    "permalink": "/r/3Dprinting/comments/abc",
                                }
                            },
                            {
                                "data": {
                                    "title": "Custom bedside stand",
                                    "subreddit": "functionalprint",
                                    "score": 450,
                                    "num_comments": 32,
                                    "permalink": "/r/functionalprint/comments/def",
                                }
                            },
                        ]
                    }
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        creds = RedditCredentials(client_id="cid", client_secret="csec")
        stats, tu = await fetch_engagement("porta celular", creds=creds, client=client)
    assert stats["posts_count"] == 2
    assert stats["posts_score"] == Decimal("1650")
    assert stats["posts_comments"] == Decimal("112")
    assert len(stats["top_posts"]) == 2
    assert stats["top_posts"][0]["permalink"].startswith("https://www.reddit.com")
    assert tu is not None
    assert tu.access_token == "rd-token"


@pytest.mark.asyncio
async def test_fetch_engagement_reuses_valid_token():
    calls = {"token": 0, "search": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/access_token":
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": "x", "expires_in": 3600})
        if request.url.path == "/search":
            calls["search"] += 1
            return httpx.Response(200, json={"data": {"children": []}})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        creds = RedditCredentials(
            client_id="cid",
            client_secret="csec",
            access_token="still-good",
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        stats, tu = await fetch_engagement("x", creds=creds, client=client)
    assert calls["token"] == 0  # no refresh
    assert calls["search"] == 1
    assert tu is None
