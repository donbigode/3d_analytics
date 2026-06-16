from calendar import monthrange
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.accounting.dre import compute_dre


def _month_iter(period_from: date, period_to: date):
    y, m = period_from.year, period_from.month
    while (y, m) <= (period_to.year, period_to.month):
        start = date(y, m, 1)
        end = date(y, m, monthrange(y, m)[1])
        yield f"{y:04d}-{m:02d}", start, end
        m += 1
        if m > 12:
            m = 1; y += 1


async def compute_dre_monthly(session: AsyncSession, period_from: date, period_to: date) -> list[dict]:
    out: list[dict] = []
    for label, start, end in _month_iter(period_from, period_to):
        dre = await compute_dre(session, start, end)
        out.append({"month": label, **dre})
    return out
