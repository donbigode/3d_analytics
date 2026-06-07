"""Trends sources panel + LLM suggestions inbox endpoints."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.infra.db import session as session_module
from backend.infra.db.models import (
    DataSourceRun,
    KeywordIdea,
    LLMSuggestion,
)


@pytest.mark.asyncio
async def test_sources_empty_state(auth_client):
    r = await auth_client.get("/trends/sources")
    assert r.status_code == 200
    body = r.json()
    names = [s["source"] for s in body["sources"]]
    assert {"google_trends", "mercadolivre", "anthropic", "gemini", "llm"}.issubset(names)
    # Google Trends is the only source enabled by default (no creds needed).
    # ML requires OAuth credentials since 2024, so it starts disabled too.
    by_name = {s["source"]: s for s in body["sources"]}
    assert by_name["google_trends"]["enabled"] is True
    assert by_name["mercadolivre"]["enabled"] is False
    assert by_name["anthropic"]["enabled"] is False


@pytest.mark.asyncio
async def test_sources_with_run_history(auth_client):
    async with session_module.SessionFactory() as s:
        s.add(
            DataSourceRun(
                source="google_trends",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                status="success",
                items_created=12,
            )
        )
        await s.commit()
    r = await auth_client.get("/trends/sources")
    by_name = {s["source"]: s for s in r.json()["sources"]}
    assert by_name["google_trends"]["runs_24h"] == 1
    assert by_name["google_trends"]["items_created_24h"] == 12
    assert by_name["google_trends"]["last_status"] == "success"


@pytest.mark.asyncio
async def test_suggestions_list_pending_only(auth_client):
    async with session_module.SessionFactory() as s:
        s.add(LLMSuggestion(term="pending one", provider="anthropic", status="pending"))
        s.add(LLMSuggestion(term="auto", provider="anthropic", status="auto_promoted"))
        s.add(LLMSuggestion(term="dismissed", provider="anthropic", status="dismissed"))
        await s.commit()
    r = await auth_client.get("/trends/suggestions")
    body = r.json()
    assert {it["term"] for it in body} == {"pending one"}


@pytest.mark.asyncio
async def test_suggestion_promote_creates_keyword(auth_client):
    async with session_module.SessionFactory() as s:
        sug = LLMSuggestion(term="abacaxi 3d", provider="anthropic", status="pending")
        s.add(sug)
        await s.commit()
        await s.refresh(sug)
        sid = str(sug.id)
    r = await auth_client.post(f"/trends/suggestions/{sid}/promote")
    assert r.status_code == 200
    body = r.json()
    assert body["term"] == "abacaxi 3d"
    # Idea exists in keyword_ideas
    async with session_module.SessionFactory() as s:
        res = await s.execute(select(KeywordIdea).where(KeywordIdea.term == "abacaxi 3d"))
        assert res.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_suggestion_dismiss(auth_client):
    async with session_module.SessionFactory() as s:
        sug = LLMSuggestion(term="x", provider="anthropic", status="pending")
        s.add(sug)
        await s.commit()
        await s.refresh(sug)
        sid = str(sug.id)
    r = await auth_client.post(f"/trends/suggestions/{sid}/dismiss")
    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"


@pytest.mark.asyncio
async def test_suggestion_promote_when_already_handled(auth_client):
    async with session_module.SessionFactory() as s:
        sug = LLMSuggestion(term="x", provider="anthropic", status="dismissed")
        s.add(sug)
        await s.commit()
        await s.refresh(sug)
        sid = str(sug.id)
    r = await auth_client.post(f"/trends/suggestions/{sid}/promote")
    assert r.status_code == 409
