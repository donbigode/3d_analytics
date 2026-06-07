from collections.abc import AsyncIterator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db.session import get_session


async def db_session() -> AsyncIterator[AsyncSession]:
    async for s in get_session():
        yield s
