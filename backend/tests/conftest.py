"""Root pytest conftest.

The pytest suite uses a dedicated database (``app_test``) so running tests
never touches the dev/prod data in ``app``. This file:

* derives the test DB URL from ``DATABASE_URL`` (swapping the dbname suffix);
* drops + recreates ``app_test`` once per pytest session;
* runs the Alembic migrations against it;
* exposes the URL as a session-scope fixture for child conftests to use.
"""

from __future__ import annotations

import asyncio
import os
import subprocess

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app import app
from backend.settings import get_settings


def _derive_test_url(base: str) -> str:
    """Replace the final '/<dbname>' in a postgresql URL with '/<dbname>_test'."""
    head, _, db = base.rpartition("/")
    if "?" in db:
        # very unlikely with our URLs but be defensive
        name, _, query = db.partition("?")
        return f"{head}/{name}_test?{query}"
    return f"{head}/{db}_test"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _derive_test_url(get_settings().database_url)


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_db(test_database_url: str):
    """Drop and recreate the test DB, then apply migrations."""
    admin_url = test_database_url.rsplit("/", 1)[0] + "/postgres"
    db_name = test_database_url.rsplit("/", 1)[1]

    async def reset_db() -> None:
        engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            async with engine.connect() as conn:
                await conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :name AND pid <> pg_backend_pid()"
                    ),
                    {"name": db_name},
                )
                await conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
                await conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        finally:
            await engine.dispose()

    asyncio.run(reset_db())

    env = os.environ.copy()
    env["DATABASE_URL"] = test_database_url
    subprocess.run(["alembic", "upgrade", "head"], env=env, check=True)
    yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
