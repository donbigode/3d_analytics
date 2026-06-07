import pytest
from sqlalchemy import select

from backend.infra.db.models import WatcherInboxFile
from backend.infra.db.session import SessionFactory
from backend.infra.watcher.runner import scan_once


@pytest.mark.asyncio
async def test_scan_once_creates_inbox(tmp_path):
    f = tmp_path / "abc.gcode"
    f.write_text(";TIME:60\n;Filament used:1.0m\n;Material Type:PLA\n")
    await scan_once(tmp_path)
    async with SessionFactory() as s:
        rows = (await s.execute(select(WatcherInboxFile))).scalars().all()
        assert any(r.original_path.endswith("abc.gcode") for r in rows)


@pytest.mark.asyncio
async def test_scan_idempotent(tmp_path):
    f = tmp_path / "x.gcode"
    f.write_text(";TIME:60\n;Filament used:1.0m\n;Material Type:PLA\n")
    await scan_once(tmp_path)
    await scan_once(tmp_path)
    async with SessionFactory() as s:
        rows = (
            await s.execute(
                select(WatcherInboxFile).where(WatcherInboxFile.original_path == str(f))
            )
        ).scalars().all()
        assert len(rows) == 1
