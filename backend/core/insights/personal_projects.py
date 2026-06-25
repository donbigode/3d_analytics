from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import QuoteKind
from backend.infra.db.models import (
    MaterialConsumption, Person, Quote, QuoteItem, QuotePerson, Sale,
)


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


async def compute_personal_projects(session: AsyncSession, period_from: date, period_to: date) -> dict:
    """Agrega projetos pessoais por pessoa no período (por created_at do orçamento).

    Projeto compartilhado (2+ pessoas) conta para cada uma; `shared_count` e
    `unassigned_count` dão a leitura honesta.
    """
    next_day = period_to + timedelta(days=1)
    quotes = (await session.execute(
        select(Quote).where(
            Quote.kind == QuoteKind.PERSONAL.value,
            Quote.created_at >= period_from,
            Quote.created_at < next_day,
        )
    )).scalars().all()
    quote_ids = [q.id for q in quotes]
    if not quote_ids:
        return {"people": [], "shared_count": 0, "unassigned_count": 0}

    qp = (await session.execute(
        select(QuotePerson).where(QuotePerson.quote_id.in_(quote_ids))
    )).scalars().all()
    people_by_quote: dict = defaultdict(list)
    for row in qp:
        people_by_quote[row.quote_id].append(row.person_id)

    grams_rows = (await session.execute(
        select(QuoteItem.quote_id, func.coalesce(func.sum(MaterialConsumption.grams_used), 0))
        .join(MaterialConsumption, MaterialConsumption.quote_item_id == QuoteItem.id)
        .where(QuoteItem.quote_id.in_(quote_ids))
        .group_by(QuoteItem.quote_id)
    )).all()
    grams_by_quote = {qid: Decimal(g) for qid, g in grams_rows}

    sales = (await session.execute(
        select(Sale).where(Sale.quote_id.in_(quote_ids), Sale.is_stale.is_(False))
    )).scalars().all()
    cpv_by_quote = {
        s.quote_id: (s.cpv_override if s.cpv_override is not None else s.cpv_calc)
        for s in sales
    }

    name_by_id = {
        p.id: p.name
        for p in (await session.execute(select(Person))).scalars().all()
    }

    agg: dict = {}
    shared = 0
    unassigned = 0
    for q in quotes:
        pids = people_by_quote.get(q.id, [])
        if not pids:
            unassigned += 1
            continue
        if len(pids) >= 2:
            shared += 1
        month = q.created_at.strftime("%Y-%m")
        g = grams_by_quote.get(q.id, Decimal(0))
        c = cpv_by_quote.get(q.id, Decimal(0))
        for pid in pids:
            a = agg.setdefault(pid, {"count": 0, "grams": Decimal(0), "cpv": Decimal(0),
                                     "monthly": defaultdict(int)})
            a["count"] += 1
            a["grams"] += g
            a["cpv"] += c
            a["monthly"][month] += 1

    people = []
    for pid, a in agg.items():
        people.append({
            "person_id": str(pid),
            "name": name_by_id.get(pid, "—"),
            "count": a["count"],
            "grams": _q2(a["grams"]),
            "cpv": _q2(a["cpv"]),
            "monthly": [{"month": m, "count": n} for m, n in sorted(a["monthly"].items())],
        })
    people.sort(key=lambda x: x["count"], reverse=True)
    return {"people": people, "shared_count": shared, "unassigned_count": unassigned}
