from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.accounting.cost import apply_markup, compute_quote_costs, load_settings_row
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db.models import Quote, Sale, Settings

# Status considerados "candidatos a venda" (a partir de aprovado).
ACTIVE_STATUSES = (
    QuoteStatus.APROVADO.value,
    QuoteStatus.PRODUZIDO.value,
    QuoteStatus.ENTREGUE.value,
)


def _status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


async def sync_sales(session: AsyncSession) -> dict[str, int]:
    """Lazy upsert dos orçamentos comerciais aprovado+ na tabela `sales`.

    Sempre reescreve os campos-espelho; nunca toca nos editáveis. Linhas cujo
    orçamento saiu de aprovado+ viram `is_stale=True` (mantém histórico).
    """
    settings_row = load_settings_row(await session.get(Settings, 1))

    quotes = (
        await session.execute(
            select(Quote).where(
                Quote.kind.in_((QuoteKind.COMMERCIAL.value, QuoteKind.PERSONAL.value)),
                Quote.status.in_(ACTIVE_STATUSES),
            )
        )
    ).scalars().all()

    existing = {
        sale.quote_id: sale
        for sale in (await session.execute(select(Sale))).scalars().all()
    }

    created = updated = stale = 0
    active_ids: set = set()

    for q in quotes:
        active_ids.add(q.id)
        costs = await compute_quote_costs(session, q, settings_row)
        total = apply_markup(costs.cost_orcado, q.markup_pct, q.min_charge)

        sale = existing.get(q.id)
        if sale is None:
            sale = Sale(quote_id=q.id, is_sold=False, variable_costs=Decimal(0))
            session.add(sale)
            created += 1
        else:
            updated += 1

        sale.quote_status = _status_value(q.status)
        sale.quote_kind = _status_value(q.kind)
        sale.quote_total = total
        sale.cpv_calc = costs.cpv
        sale.client_id = q.client_id
        sale.is_stale = False

    for quote_id, sale in existing.items():
        if quote_id not in active_ids and not sale.is_stale:
            sale.is_stale = True
            stale += 1

    await session.commit()
    return {"created": created, "updated": updated, "stale": stale}
