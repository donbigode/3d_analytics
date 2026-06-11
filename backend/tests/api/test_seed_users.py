import pytest
from sqlalchemy import select

from backend.infra.db.models import User


@pytest.mark.asyncio
async def test_seed_users_creates_two_with_must_change_flag(db_session, monkeypatch):
    monkeypatch.setenv("SEED_USER_OTAVIO_EMAIL", "otaviorgeraldo@gmail.com")
    monkeypatch.setenv("SEED_USER_ANA_EMAIL", "anarqborges@gmail.com")
    monkeypatch.setenv("SEED_INITIAL_PASSWORD", "F1odor_213")

    from backend.scripts.seed_users import run_seed
    n = await run_seed(db_session)
    assert n == 2

    rows = (await db_session.execute(select(User).order_by(User.email))).scalars().all()
    emails = {u.email for u in rows}
    assert "anarqborges@gmail.com" in emails
    assert "otaviorgeraldo@gmail.com" in emails
    for u in rows:
        if u.email in ("anarqborges@gmail.com", "otaviorgeraldo@gmail.com"):
            assert u.must_change_password is True


@pytest.mark.asyncio
async def test_seed_users_idempotent(db_session, monkeypatch):
    monkeypatch.setenv("SEED_USER_OTAVIO_EMAIL", "otaviorgeraldo@gmail.com")
    monkeypatch.setenv("SEED_USER_ANA_EMAIL", "anarqborges@gmail.com")
    monkeypatch.setenv("SEED_INITIAL_PASSWORD", "F1odor_213")

    from backend.scripts.seed_users import run_seed
    await run_seed(db_session)
    # Rodar de novo não deve duplicar nem trocar a senha de quem já existe.
    n2 = await run_seed(db_session)
    assert n2 == 0  # zero novos inserts

    rows = (await db_session.execute(select(User).where(User.email == "otaviorgeraldo@gmail.com"))).scalars().all()
    assert len(rows) == 1
