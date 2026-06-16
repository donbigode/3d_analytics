"""Per-test SQLAlchemy engine + DB cleanup for core tests that touch the DB.

Most core tests are pure logic and never open a session. The accounting tests
(cost/sync/dre) do hit the DB, and some aggregate *all* rows in a period — so
they need isolation. This mirrors backend/tests/api/conftest.py:
  - rebind ``SessionFactory`` to a per-test NullPool engine (avoids the
    "attached to a different loop" error pytest-asyncio causes);
  - delete rows created during the test so they don't bleed into the next one.
"""

from __future__ import annotations

import sys

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.infra.db import session as session_module
from backend.infra.db.models import (
    Client,
    Expense,
    MaterialConsumption,
    MaterialVersion,
    Quote,
    QuoteItem,
    QuoteService,
    Sale,
    Settings,
    Spool,
    User,
)


@pytest.fixture(autouse=True)
async def _isolated_engine_core(test_database_url):
    engine = create_async_engine(test_database_url, future=True, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    original_engine = session_module.engine
    original_factory = session_module.SessionFactory
    session_module.engine = engine
    session_module.SessionFactory = factory

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
                    MaterialConsumption.__table__,
                    QuoteService.__table__,
                    QuoteItem.__table__,
                    Sale.__table__,
                    Expense.__table__,
                    Quote.__table__,
                    Spool.__table__,
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
        for mod, attr, original in patched:
            setattr(mod, attr, original)
        session_module.engine = original_engine
        session_module.SessionFactory = original_factory
