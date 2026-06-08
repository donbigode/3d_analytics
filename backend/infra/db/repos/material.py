"""Material repository — UUID-keyed access with SCD2 versioning.

A "material" is identified by its UUID. Each material has a polymer
``material_type`` (PLA/PETG/…) that's used to match gcode headers, plus
optional ``manufacturer`` and ``color`` so the user can distinguish
"Voolt PLA Preto" from "Esun PLA Branco" even though both match
``material_type='PLA'``.

When the gcode resolution finds multiple current materials for the same
type, the QuoteItem is left in a pending state — the user picks one via
``PUT /quotes/{id}/items/{item_id}`` with the chosen material's UUID.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db.models import MaterialVersion


async def get_by_id(session: AsyncSession, material_id: UUID) -> MaterialVersion | None:
    return await session.get(MaterialVersion, material_id)


async def current_by_type(session: AsyncSession, material_type: str) -> list[MaterialVersion]:
    """Return ALL current materials matching the polymer type."""
    res = await session.execute(
        select(MaterialVersion).where(
            MaterialVersion.material_type == material_type,
            MaterialVersion.is_current.is_(True),
        )
    )
    return list(res.scalars())


async def auto_resolve_for_gcode(
    session: AsyncSession, material_type: str
) -> MaterialVersion | None:
    """Pick a current MaterialVersion for a freshly-uploaded gcode.

    Returns the only match when there's exactly one current row of that type;
    otherwise returns None so the QuoteItem stays pending.
    """
    matches = await current_by_type(session, material_type)
    if len(matches) == 1:
        return matches[0]
    return None


async def list_current(session: AsyncSession) -> list[MaterialVersion]:
    res = await session.execute(
        select(MaterialVersion)
        .where(MaterialVersion.is_current.is_(True))
        .order_by(MaterialVersion.material_type, MaterialVersion.manufacturer, MaterialVersion.color)
    )
    return list(res.scalars())


async def create_initial(session: AsyncSession, **fields) -> MaterialVersion:
    """Create a new material. No global uniqueness check — same (type, mfr,
    color) combination is allowed because the user might split the same product
    across rolls of different vintages."""
    mv = MaterialVersion(**fields, is_current=True)
    session.add(mv)
    await session.commit()
    await session.refresh(mv)
    return mv


async def new_version(
    session: AsyncSession, material_id: UUID, **changes
) -> MaterialVersion:
    """SCD2: close the current row identified by ``material_id`` and create a
    new current one carrying over unchanged fields."""
    cur = await session.get(MaterialVersion, material_id)
    if not cur or not cur.is_current:
        raise ValueError("material not found or not current")
    cur.is_current = False
    cur.effective_to = datetime.now(timezone.utc)
    new = MaterialVersion(
        material_type=cur.material_type,
        name=changes.get("name", cur.name),
        manufacturer=changes.get("manufacturer", cur.manufacturer),
        color=changes.get("color", cur.color),
        density_g_cm3=changes.get("density_g_cm3", cur.density_g_cm3),
        price_per_kg_ref=changes.get("price_per_kg_ref", cur.price_per_kg_ref),
        failure_rate_pct=changes.get("failure_rate_pct", cur.failure_rate_pct),
        is_current=True,
    )
    session.add(new)
    await session.commit()
    await session.refresh(new)
    return new


async def history(session: AsyncSession, material_id: UUID) -> list[MaterialVersion]:
    """All versions that share the same product line as ``material_id``.

    Two rows belong to the same product line if their (type, manufacturer,
    color) trio matches. We find the seed by id, then list rows with the
    same trio sorted by effective_from.
    """
    seed = await session.get(MaterialVersion, material_id)
    if seed is None:
        return []
    res = await session.execute(
        select(MaterialVersion)
        .where(
            MaterialVersion.material_type == seed.material_type,
            MaterialVersion.manufacturer.is_(seed.manufacturer)
            if seed.manufacturer is None
            else MaterialVersion.manufacturer == seed.manufacturer,
            MaterialVersion.color.is_(seed.color)
            if seed.color is None
            else MaterialVersion.color == seed.color,
        )
        .order_by(MaterialVersion.effective_from)
    )
    return list(res.scalars())
