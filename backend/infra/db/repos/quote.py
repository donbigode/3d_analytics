from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db.models import Quote, QuoteItem, QuoteService


async def get_quote(session: AsyncSession, quote_id: UUID) -> Quote | None:
    return await session.get(Quote, quote_id)


async def list_items(session: AsyncSession, quote_id: UUID) -> list[QuoteItem]:
    res = await session.execute(
        select(QuoteItem)
        .where(QuoteItem.quote_id == quote_id)
        .order_by(QuoteItem.id)
    )
    return list(res.scalars())


async def list_services(session: AsyncSession, quote_id: UUID) -> list[QuoteService]:
    res = await session.execute(
        select(QuoteService)
        .where(QuoteService.quote_id == quote_id)
        .order_by(QuoteService.id)
    )
    return list(res.scalars())
