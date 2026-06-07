import asyncio
import hashlib
from pathlib import Path

from sqlalchemy import select
from watchfiles import awatch

from backend.core.gcode.parser import parse_gcode_metadata
from backend.infra.db import session as _db_session
from backend.infra.db.models import WatcherInboxFile


def _hash_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


async def _process_file(p: Path) -> None:
    if p.suffix.lower() != ".gcode" or not p.is_file():
        return
    digest = _hash_file(p)
    async with _db_session.SessionFactory() as s:
        existing = await s.scalar(
            select(WatcherInboxFile).where(WatcherInboxFile.file_hash == digest)
        )
        if existing:
            return
        try:
            meta = parse_gcode_metadata(p)
        except ValueError:
            return
        s.add(
            WatcherInboxFile(
                file_hash=digest,
                original_path=str(p),
                parsed_meta={
                    "time_s": meta.time_s,
                    "filament_m": meta.filament_m,
                    "material": meta.material,
                    "machine": meta.machine,
                },
            )
        )
        await s.commit()


async def scan_once(directory: Path) -> None:
    for p in directory.glob("*.gcode"):
        await _process_file(p)


async def run_forever(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    await scan_once(directory)
    async for changes in awatch(str(directory)):
        for _change_type, path in changes:
            await _process_file(Path(path))


def start_background_task(directory_path: str) -> asyncio.Task:
    return asyncio.create_task(run_forever(Path(directory_path)))
