"""Per-test SQLAlchemy engine + DB cleanup for API tests.

Mirrors the pattern from backend/tests/infra/conftest.py so that:
  - the async engine is bound to the test's event loop (avoids "different loop" errors)
  - rows from one test don't bleed into the next (avoids unique-constraint clashes)
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app import app
from backend.core.security import hash_password
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    Client,
    MaterialConsumption,
    MaterialVersion,
    Quote,
    QuoteItem,
    QuoteService,
    Service,
    Settings,
    Spool,
    User,
    WatcherInboxFile,
)
from backend.settings import get_settings


@pytest.fixture(autouse=True)
async def _isolated_engine_api():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, future=True, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    original_engine = session_module.engine
    original_factory = session_module.SessionFactory
    session_module.engine = engine
    session_module.SessionFactory = factory
    try:
        yield
    finally:
        try:
            async with factory() as s:
                # order matters: delete dependents before parents
                for table in (
                    MaterialConsumption.__table__,
                    QuoteService.__table__,
                    QuoteItem.__table__,
                    WatcherInboxFile.__table__,
                    Quote.__table__,
                    Spool.__table__,
                    Service.__table__,
                    MaterialVersion.__table__,
                    Client.__table__,
                    User.__table__,
                    Settings.__table__,
                ):
                    await s.execute(table.delete())
                await s.commit()
        except Exception:
            pass
        await engine.dispose()
        session_module.engine = original_engine
        session_module.SessionFactory = original_factory


@pytest.fixture
async def auth_client():
    async with session_module.SessionFactory() as s:
        u = User(name="t", email="t@t.com", password_hash=hash_password("pw"))
        s.add(u); await s.commit()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/auth/login", json={"email": "t@t.com", "password": "pw"})
        yield c
