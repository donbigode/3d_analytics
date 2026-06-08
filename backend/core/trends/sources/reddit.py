"""Reddit search adapter — OAuth client_credentials.

The anonymous ``/search.json`` endpoint was closed off in 2024-2025; even
with a real User-Agent Reddit serves the HTML page instead of JSON. You
need a "script" app at https://www.reddit.com/prefs/apps to get a
client_id + client_secret, which we exchange for a Bearer token here.

Endpoint after OAuth:
  https://oauth.reddit.com/search?q=<term>&limit=25&sort=hot&t=week

The adapter mirrors the Mercado Livre OAuth pattern: caller passes credentials
(possibly with a cached token), we refresh when stale, return a tuple of
``(engagement_dict, token_update_or_None)`` so the scheduler persists the
refreshed token. Returns ``({}, None)`` when credentials are missing or any
HTTP error occurs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)

REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
REDDIT_SEARCH_URL = "https://oauth.reddit.com/search"
USER_AGENT = "3d-analytics/0.1 (by /u/3d-analytics-radar)"
_TIMEOUT = httpx.Timeout(15.0)


@dataclass(frozen=True)
class RedditCredentials:
    client_id: str
    client_secret: str
    access_token: str | None = None
    token_expires_at: datetime | None = None


@dataclass(frozen=True)
class RedditTokenUpdate:
    access_token: str
    expires_at: datetime


def _is_token_valid(creds: RedditCredentials) -> bool:
    if not creds.access_token or not creds.token_expires_at:
        return False
    return creds.token_expires_at > datetime.now(timezone.utc) + timedelta(seconds=60)


async def _refresh_token(
    creds: RedditCredentials, *, client: httpx.AsyncClient
) -> RedditTokenUpdate | None:
    try:
        r = await client.post(
            REDDIT_TOKEN_URL,
            data={"grant_type": "client_credentials"},
            auth=(creds.client_id, creds.client_secret),
            headers={"User-Agent": USER_AGENT, "accept": "application/json"},
        )
        r.raise_for_status()
        body = r.json()
    except Exception as exc:
        logger.warning("reddit token refresh failed: %s", exc)
        return None
    access_token = body.get("access_token")
    expires_in = int(body.get("expires_in") or 0)
    if not access_token or expires_in <= 0:
        return None
    return RedditTokenUpdate(
        access_token=access_token,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
    )


async def fetch_engagement(
    term: str,
    *,
    creds: RedditCredentials | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, Any], RedditTokenUpdate | None]:
    """Search Reddit and aggregate engagement across the top-25 results."""

    if creds is None or not creds.client_id or not creds.client_secret:
        return {}, None

    own = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=_TIMEOUT)

    token_update: RedditTokenUpdate | None = None
    try:
        access_token = creds.access_token
        if not _is_token_valid(creds):
            refreshed = await _refresh_token(creds, client=client)
            if refreshed is None:
                return {}, None
            access_token = refreshed.access_token
            token_update = refreshed

        try:
            r = await client.get(
                REDDIT_SEARCH_URL,
                params={"q": term, "limit": 25, "sort": "hot", "t": "week"},
                headers={
                    "User-Agent": USER_AGENT,
                    "Authorization": f"Bearer {access_token}",
                    "accept": "application/json",
                },
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.warning("reddit search failed for %r: %s", term, exc)
            return {}, token_update

        children = ((data or {}).get("data") or {}).get("children") or []
        if not children:
            return (
                {
                    "posts_count": 0,
                    "posts_score": Decimal("0"),
                    "posts_comments": Decimal("0"),
                    "top_posts": [],
                },
                token_update,
            )

        score_sum = Decimal("0")
        comments_sum = Decimal("0")
        top_posts: list[dict[str, Any]] = []

        for ch in children:
            d = ch.get("data") or {}
            try:
                sc = int(d.get("score") or 0)
                co = int(d.get("num_comments") or 0)
            except (TypeError, ValueError):
                continue
            score_sum += Decimal(sc)
            comments_sum += Decimal(co)
            if len(top_posts) < 5:
                permalink = d.get("permalink") or ""
                top_posts.append(
                    {
                        "title": d.get("title") or "",
                        "subreddit": d.get("subreddit") or "",
                        "score": sc,
                        "comments": co,
                        "permalink": (
                            f"https://www.reddit.com{permalink}"
                            if permalink.startswith("/")
                            else permalink
                        ),
                    }
                )

        return (
            {
                "posts_count": len(children),
                "posts_score": score_sum,
                "posts_comments": comments_sum,
                "top_posts": top_posts,
            },
            token_update,
        )
    finally:
        if own:
            await client.aclose()
