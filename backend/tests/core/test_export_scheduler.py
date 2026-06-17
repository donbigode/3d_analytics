import pytest

import backend.infra.scheduler.export as sched
from backend.infra.db import session as session_module
from backend.infra.db.models import ExportConfig


@pytest.mark.asyncio
async def test_export_once_respects_enabled(monkeypatch):
    calls = {"n": 0}

    async def fake_execute(session):
        calls["n"] += 1
        return {"ok": True}
    monkeypatch.setattr(sched, "execute_export", fake_execute)

    # desabilitado -> não roda
    async with session_module.SessionFactory() as s:
        await s.merge(ExportConfig(id=1, enabled=False, destination="s3", s3_bucket="b"))
        await s.commit()
    await sched.export_once()
    assert calls["n"] == 0

    # habilitado -> roda
    async with session_module.SessionFactory() as s:
        await s.merge(ExportConfig(id=1, enabled=True, destination="s3", s3_bucket="b"))
        await s.commit()
    await sched.export_once()
    assert calls["n"] == 1
