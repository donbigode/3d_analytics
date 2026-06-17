import asyncio

from backend.core.export.runner import execute_export
from backend.infra.db import session as session_module
from backend.infra.db.models import ExportConfig

ONE_DAY_SECONDS = 24 * 60 * 60


async def export_once() -> None:
    """Roda o export se o envio diário estiver habilitado."""
    async with session_module.SessionFactory() as session:
        cfg = await session.get(ExportConfig, 1)
        if cfg is None or not cfg.enabled:
            return
    async with session_module.SessionFactory() as session:
        await execute_export(session)


async def run_forever() -> None:
    while True:
        try:
            await export_once()
        except Exception:
            pass
        await asyncio.sleep(ONE_DAY_SECONDS)


def start_background_task() -> asyncio.Task:
    return asyncio.create_task(run_forever())
