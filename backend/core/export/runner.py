import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.export.destinations import Destination, build_destination
from backend.core.export.entities import EXPORT_ENTITIES, columns_for
from backend.core.export.serialize import table_to_parquet
from backend.infra.db.models import ExportConfig


async def run_export(session: AsyncSession, destination: Destination) -> dict:
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    counts: dict[str, int] = {}
    for entry in EXPORT_ENTITIES:
        name, model, _excluded = entry
        cols = columns_for(entry)
        objs = (await session.execute(select(model))).scalars().all()
        rows = [{c: getattr(o, c) for c in cols} for o in objs]
        data = table_to_parquet(rows, cols)
        await asyncio.to_thread(destination.put, f"{run_ts}/{name}.parquet", data)
        counts[name] = len(rows)
    return {"run_ts": run_ts, "counts": counts}


async def execute_export(session: AsyncSession) -> dict:
    """Carrega a config, monta o destino, roda o export e grava last_run_*."""
    cfg = await session.get(ExportConfig, 1)
    if cfg is None:
        cfg = ExportConfig(id=1)
        session.add(cfg)
        await session.commit()
    try:
        dest = build_destination(cfg)
        summary = await run_export(session, dest)
        cfg.last_run_at = datetime.now(timezone.utc)
        cfg.last_run_status = "ok"
        cfg.last_run_detail = json.dumps(summary["counts"])
        await session.commit()
        return {"ok": True, **summary}
    except Exception as exc:  # destino/credencial/serialização
        cfg.last_run_at = datetime.now(timezone.utc)
        cfg.last_run_status = "error"
        cfg.last_run_detail = str(exc)
        await session.commit()
        return {"ok": False, "detail": str(exc)}
