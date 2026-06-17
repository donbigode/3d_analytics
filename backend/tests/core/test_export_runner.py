from decimal import Decimal

import pytest

from backend.core.export.runner import execute_export, run_export
import backend.core.export.runner as runner_mod
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import ExportConfig, Quote, User


class FakeDestination:
    def __init__(self):
        self.puts = {}

    def put(self, rel_path, data):
        self.puts[rel_path] = data


@pytest.mark.asyncio
async def test_run_export_one_file_per_entity():
    async with session_module.SessionFactory() as s:
        u = User(name="u", email="exp@t.com", password_hash="x")
        s.add(u); await s.commit()
        s.add(Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                    status=QuoteStatus.APROVADO.value, markup_pct=Decimal("0"), min_charge=Decimal("0")))
        await s.commit()

    dest = FakeDestination()
    async with session_module.SessionFactory() as s:
        summary = await run_export(s, dest)

    # um arquivo por entidade, todos sob a mesma pasta run_ts
    assert any(p.endswith("/quotes.parquet") for p in dest.puts)
    assert any(p.endswith("/users.parquet") for p in dest.puts)
    run_ts = summary["run_ts"]
    assert all(p.startswith(f"{run_ts}/") for p in dest.puts)
    assert summary["counts"]["quotes"] >= 1


@pytest.mark.asyncio
async def test_execute_export_records_status(monkeypatch):
    async with session_module.SessionFactory() as s:
        await s.merge(ExportConfig(id=1, destination="s3", s3_bucket="b"))
        await s.commit()

    dest = FakeDestination()
    monkeypatch.setattr(runner_mod, "build_destination", lambda cfg: dest)

    async with session_module.SessionFactory() as s:
        res = await execute_export(s)
    assert res["ok"] is True

    async with session_module.SessionFactory() as s:
        cfg = await s.get(ExportConfig, 1)
        assert cfg.last_run_status == "ok"
        assert cfg.last_run_at is not None


@pytest.mark.asyncio
async def test_execute_export_error_path(monkeypatch):
    async with session_module.SessionFactory() as s:
        await s.merge(ExportConfig(id=1, destination="s3", s3_bucket="b"))
        await s.commit()

    def boom(cfg):
        raise ValueError("sem credencial")
    monkeypatch.setattr(runner_mod, "build_destination", boom)

    async with session_module.SessionFactory() as s:
        res = await execute_export(s)
    assert res["ok"] is False
    assert "sem credencial" in res["detail"]
    async with session_module.SessionFactory() as s:
        cfg = await s.get(ExportConfig, 1)
        assert cfg.last_run_status == "error"
