from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db.models import MaterialVersion


async def current(session: AsyncSession, material_code: str) -> MaterialVersion | None:
    res = await session.execute(
        select(MaterialVersion).where(
            MaterialVersion.material_code == material_code,
            MaterialVersion.is_current.is_(True),
        )
    )
    return res.scalar_one_or_none()


async def list_current(session: AsyncSession) -> list[MaterialVersion]:
    res = await session.execute(
        select(MaterialVersion).where(MaterialVersion.is_current.is_(True))
        .order_by(MaterialVersion.material_code)
    )
    return list(res.scalars())


async def create_initial(session: AsyncSession, **fields) -> MaterialVersion:
    existing = await current(session, fields["material_code"])
    if existing:
        raise ValueError("material already exists")
    mv = MaterialVersion(**fields, is_current=True)
    session.add(mv); await session.commit(); await session.refresh(mv)
    return mv


async def new_version(session: AsyncSession, material_code: str, **changes) -> MaterialVersion:
    cur = await current(session, material_code)
    if not cur:
        raise ValueError("material not found")
    cur.is_current = False
    cur.effective_to = datetime.now(timezone.utc)
    new = MaterialVersion(
        material_code=cur.material_code,
        name=changes.get("name", cur.name),
        density_g_cm3=changes.get("density_g_cm3", cur.density_g_cm3),
        price_per_kg_ref=changes.get("price_per_kg_ref", cur.price_per_kg_ref),
        failure_rate_pct=changes.get("failure_rate_pct", cur.failure_rate_pct),
        is_current=True,
    )
    session.add(new); await session.commit(); await session.refresh(new)
    return new


async def history(session: AsyncSession, material_code: str) -> list[MaterialVersion]:
    res = await session.execute(
        select(MaterialVersion).where(MaterialVersion.material_code == material_code)
        .order_by(MaterialVersion.effective_from)
    )
    return list(res.scalars())
