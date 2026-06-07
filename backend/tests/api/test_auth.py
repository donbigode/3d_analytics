import pytest
from uuid import uuid4
from backend.core.security import hash_password
from backend.infra.db.session import SessionFactory
from backend.infra.db.models import User


@pytest.fixture
async def user_in_db():
    async with SessionFactory() as s:
        u = User(id=uuid4(), name="Otavio", email="o@x.com", password_hash=hash_password("hunter2"))
        s.add(u); await s.commit()
        yield u


@pytest.mark.asyncio
async def test_login_ok(client, user_in_db):
    r = await client.post("/auth/login", json={"email": "o@x.com", "password": "hunter2"})
    assert r.status_code == 200
    assert "session" in r.cookies


@pytest.mark.asyncio
async def test_login_fail(client, user_in_db):
    r = await client.post("/auth/login", json={"email": "o@x.com", "password": "wrong"})
    assert r.status_code == 401
