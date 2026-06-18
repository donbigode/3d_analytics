"""Per-test SQLAlchemy engine + DB cleanup for API tests.

Mirrors the pattern from backend/tests/infra/conftest.py so that:
  - the async engine is bound to the test's event loop (avoids "different loop" errors)
  - rows from one test don't bleed into the next (avoids unique-constraint clashes)
"""

from __future__ import annotations

import sys

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app import app
from backend.core.security import hash_password
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    Asset,
    CalibrationInsight,
    Client,
    DataSourceRun,
    Expense,
    ExportConfig,
    KeywordIdea,
    KeywordObservation,
    LLMSuggestion,
    MaterialConsumption,
    MaterialVersion,
    Quote,
    QuoteItem,
    QuotePhoto,
    QuoteService,
    Sale,
    Service,
    Settings,
    Spool,
    User,
    WatcherInboxFile,
)


@pytest.fixture(autouse=True)
async def _isolated_engine_api(test_database_url):
    engine = create_async_engine(test_database_url, future=True, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    original_engine = session_module.engine
    original_factory = session_module.SessionFactory
    session_module.engine = engine
    session_module.SessionFactory = factory

    # Patch any test module that imported SessionFactory by name
    patched: list[tuple[object, str, object]] = []
    for mod in list(sys.modules.values()):
        if mod is None or not getattr(mod, "__name__", "").startswith("backend.tests."):
            continue
        if getattr(mod, "SessionFactory", None) is original_factory:
            patched.append((mod, "SessionFactory", mod.SessionFactory))
            mod.SessionFactory = factory

    try:
        yield
    finally:
        try:
            async with factory() as s:
                # order matters: delete dependents before parents
                for table in (
                    QuotePhoto.__table__,
                    MaterialConsumption.__table__,
                    QuoteService.__table__,
                    QuoteItem.__table__,
                    Asset.__table__,
                    WatcherInboxFile.__table__,
                    Sale.__table__,
                    Expense.__table__,
                    Quote.__table__,
                    Spool.__table__,
                    Service.__table__,
                    MaterialVersion.__table__,
                    Client.__table__,
                    LLMSuggestion.__table__,  # FK to KeywordIdea — delete first
                    KeywordObservation.__table__,
                    KeywordIdea.__table__,
                    DataSourceRun.__table__,
                    User.__table__,
                    Settings.__table__,
                    ExportConfig.__table__,
                    CalibrationInsight.__table__,
                ):
                    await s.execute(table.delete())
                await s.commit()
        except Exception:
            pass
        await engine.dispose()
        for mod, attr, original in patched:
            setattr(mod, attr, original)
        session_module.engine = original_engine
        session_module.SessionFactory = original_factory


@pytest.fixture
async def db_session():
    async with session_module.SessionFactory() as s:
        yield s


@pytest.fixture
async def auth_client():
    async with session_module.SessionFactory() as s:
        u = User(name="t", email="t@t.com", password_hash=hash_password("pw"))
        s.add(u); await s.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/auth/login", json={"email": "t@t.com", "password": "pw"})
        yield c
