"""Per-test SQLAlchemy engine to avoid 'attached to a different loop' errors.

pytest-asyncio creates a fresh event loop for each test by default. The module-level
async engine in ``backend.infra.db.session`` binds its connection pool to the first
loop that touches it, which then breaks on subsequent tests. To keep the tests
isolated without touching production code, we rebind ``SessionFactory`` to a new
NullPool engine per test (no connection reuse → no cross-loop binding) and dispose
it after the test completes. We also rebind the same names in any test module that
imports them by name so monkey-patching is effective regardless of import style.
"""

from __future__ import annotations

import sys

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.infra.db import session as session_module
from backend.infra.db.models import WatcherInboxFile
@pytest.fixture(autouse=True)
async def _isolated_engine(test_database_url):
    engine = create_async_engine(test_database_url, future=True, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    original_engine = session_module.engine
    original_factory = session_module.SessionFactory
    session_module.engine = engine
    session_module.SessionFactory = factory

    # Also patch any test module that imported SessionFactory by name.
    patched_test_modules: list[tuple[object, str, object]] = []
    for mod in list(sys.modules.values()):
        if mod is None or not getattr(mod, "__name__", "").startswith("backend.tests."):
            continue
        if getattr(mod, "SessionFactory", None) is original_factory:
            patched_test_modules.append((mod, "SessionFactory", mod.SessionFactory))
            mod.SessionFactory = factory

    try:
        yield
    finally:
        # cleanup rows created during this test so the DB is clean for the next
        try:
            async with factory() as s:
                await s.execute(WatcherInboxFile.__table__.delete())
                await s.commit()
        except Exception:
            pass
        await engine.dispose()
        session_module.engine = original_engine
        session_module.SessionFactory = original_factory
        for mod, attr, old in patched_test_modules:
            setattr(mod, attr, old)
