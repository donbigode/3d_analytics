from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.core.accounting.cost import compute_quote_costs, load_settings_row
from backend.core.accounting.sync import sync_sales
from backend.core.accounting.dre import sale_cpv, _custo_estoque, _perda_operacional
from backend.api.schemas.dashboard import (
    CardEstoque,
    DashboardCards,
    DashboardCharts,
    DashboardLists,
    DashboardOut,
)
from backend.core.models import (
    QuoteKind,
    QuoteStatus,
    SpoolStatus,
    WatcherInboxStatus,
)
from backend.infra.db.models import (
    Expense,
    Quote,
    Sale,
    Settings,
    Spool,
    User,
    WatcherInboxFile,
)

router = APIRouter()


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


def _bucket_mode(period_from: datetime, period_to: datetime) -> str:
    """Pick day/week/month granularity for the receita_vs_despesa chart."""
    span = (period_to - period_from).days
    if span <= 14:
        return "day"
    if span <= 60:
        return "week"
    return "month"


def _bucket_key(dt: datetime, mode: str) -> str:
    if mode == "day":
        return dt.strftime("%Y-%m-%d")
    if mode == "week":
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return dt.strftime("%Y-%m")


@router.get("", response_model=DashboardOut)
async def dashboard(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    kind: QuoteKind | None = Query(None),
):
    settings_row = load_settings_row(await session.get(Settings, 1))

    now = datetime.now(timezone.utc)
    period_from = from_ or (now - timedelta(days=30))
    period_to = to or now

    await sync_sales(session)
    pf_date = period_from.date()
    pt_date = period_to.date()

    # ---------- quotes in period ----------
    q_stmt = select(Quote).where(
        Quote.created_at >= period_from,
        Quote.created_at <= period_to,
    )
    if kind is not None:
        q_stmt = q_stmt.where(Quote.kind == kind.value)
    quotes = (await session.execute(q_stmt)).scalars().all()

    receita = Decimal(0)
    despesa = Decimal(0)
    gasto_pessoal = Decimal(0)
    estado_counts: dict[str, int] = {st.value: 0 for st in QuoteStatus}

    # Charts G1 + G3 + G6 are built up during the same loop.
    bucket_mode = _bucket_mode(period_from, period_to)
    cat_totals = {
        "filamento": Decimal(0),
        "energia": Decimal(0),
        "mao_obra": Decimal(0),
        "depreciacao": Decimal(0),
    }
    orcado_vs_real_rows: list[dict] = []

    for q in quotes:
        # status is stored as str-enum value
        status_key = q.status.value if hasattr(q.status, "value") else str(q.status)
        if status_key in estado_counts:
            estado_counts[status_key] += 1

        costs = await compute_quote_costs(session, q, settings_row)
        item_energy = costs.energy
        item_dep = costs.depreciation
        services_cost = costs.services
        cost_orcado = costs.cost_orcado

        # Despesa real: commercial produzido+ uses MaterialConsumption snapshots
        is_commercial_produced = q.kind == QuoteKind.COMMERCIAL.value and status_key in (
            QuoteStatus.PRODUZIDO.value,
            QuoteStatus.ENTREGUE.value,
        )
        if is_commercial_produced:
            real_filament = costs.real_filament
            real_cost = costs.cpv

            # G3: despesa por categoria (real)
            cat_totals["filamento"] += real_filament
            cat_totals["energia"] += item_energy
            cat_totals["mao_obra"] += services_cost
            cat_totals["depreciacao"] += item_dep

            # G6: orçado (catalog-priced cost) vs real (consumption-based)
            variancia = Decimal(0)
            if cost_orcado > 0:
                variancia = (real_cost - cost_orcado) / cost_orcado * Decimal(100)
            orcado_vs_real_rows.append(
                {
                    "quote_id": str(q.id),
                    "orcado": float(_q2(cost_orcado)),
                    "real": float(_q2(real_cost)),
                    "variancia_pct": float(_q2(variancia)),
                }
            )

        # Gasto pessoal: personal produzido
        if q.kind == QuoteKind.PERSONAL.value and status_key == QuoteStatus.PRODUZIDO.value:
            real_filament_p = costs.real_filament
            real_cost_p = costs.cpv
            gasto_pessoal += real_cost_p
            # Personal also contributes to category breakdown (it's still an expense)
            cat_totals["filamento"] += real_filament_p
            cat_totals["energia"] += item_energy
            cat_totals["mao_obra"] += services_cost
            cat_totals["depreciacao"] += item_dep

    confirmed = (
        await session.execute(
            select(Sale).where(
                Sale.is_sold.is_(True),
                Sale.is_stale.is_(False),
                Sale.sold_at.is_not(None),
                Sale.sold_at >= pf_date,
                Sale.sold_at <= pt_date,
            )
        )
    ).scalars().all()
    receita = sum((s.confirmed_revenue or Decimal(0) for s in confirmed), Decimal(0))
    despesa_vendas = sum((sale_cpv(s) + s.variable_costs for s in confirmed), Decimal(0))

    op_expenses = (
        await session.execute(
            select(Expense).where(
                Expense.incurred_at >= pf_date,
                Expense.incurred_at <= pt_date,
            )
        )
    ).scalars().all()
    despesa_ops = sum((e.amount for e in op_expenses), Decimal(0))
    custo_estoque = await _custo_estoque(session, pf_date, pt_date)
    perda_operacional = await _perda_operacional(session, pf_date, pt_date)
    despesa = despesa_vendas + despesa_ops + custo_estoque + perda_operacional
    settings_tax = await session.get(Settings, 1)
    tax_pct = settings_tax.revenue_tax_pct if settings_tax else Decimal(0)
    impostos = receita * tax_pct / Decimal(100)

    # Gráfico receita_vs_despesa: receita+custo de venda por sold_at; despesa op. por incurred_at
    rev_exp_buckets = {}
    for s in confirmed:
        bk = _bucket_key(datetime(s.sold_at.year, s.sold_at.month, s.sold_at.day), bucket_mode)
        slot = rev_exp_buckets.setdefault(bk, {"receita": Decimal(0), "despesa": Decimal(0)})
        slot["receita"] += s.confirmed_revenue or Decimal(0)
        slot["despesa"] += sale_cpv(s) + s.variable_costs
    for e in op_expenses:
        bk = _bucket_key(datetime(e.incurred_at.year, e.incurred_at.month, e.incurred_at.day), bucket_mode)
        slot = rev_exp_buckets.setdefault(bk, {"receita": Decimal(0), "despesa": Decimal(0)})
        slot["despesa"] += e.amount
    if custo_estoque or perda_operacional:
        bk = _bucket_key(datetime(pt_date.year, pt_date.month, pt_date.day), bucket_mode)
        slot = rev_exp_buckets.setdefault(bk, {"receita": Decimal(0), "despesa": Decimal(0)})
        slot["despesa"] += custo_estoque + perda_operacional

    lucro = receita - despesa - impostos
    margem = (lucro / receita * Decimal(100)) if receita > 0 else Decimal(0)

    orcado_n = estado_counts.get(QuoteStatus.ORCADO.value, 0)
    aprov_n = (
        estado_counts.get(QuoteStatus.APROVADO.value, 0)
        + estado_counts.get(QuoteStatus.PRODUZIDO.value, 0)
        + estado_counts.get(QuoteStatus.ENTREGUE.value, 0)
    )
    denom = orcado_n + aprov_n
    conversion = (
        Decimal(aprov_n) / Decimal(denom) * Decimal(100) if denom > 0 else Decimal(0)
    )

    # ---------- spools (estoque) ----------
    spools = (
        await session.execute(select(Spool).where(Spool.status == SpoolStatus.OPEN.value))
    ).scalars().all()
    total_grams = sum((sp.remaining_grams for sp in spools), Decimal(0))
    estimated_value = sum(
        (
            (sp.remaining_grams / sp.initial_grams) * sp.purchased_price
            for sp in spools
            if sp.initial_grams and sp.initial_grams > 0
        ),
        Decimal(0),
    )

    # ---------- listas ----------
    ultimos = [
        {
            "id": str(q.id),
            "kind": q.kind,
            "status": q.status,
            "created_at": q.created_at.isoformat() if q.created_at else None,
        }
        for q in quotes[:10]
    ]

    parados_ts = now - timedelta(days=settings_row.stalled_quote_alert_days)
    parados_q = (
        await session.execute(
            select(Quote).where(
                Quote.status == QuoteStatus.APROVADO.value,
                Quote.approved_at < parados_ts,
            )
        )
    ).scalars().all()
    parados = [
        {
            "id": str(q.id),
            "approved_at": q.approved_at.isoformat() if q.approved_at else None,
        }
        for q in parados_q
    ]

    low_spools = [
        {
            "id": str(sp.id),
            "material_type": sp.material_type,
            "remaining_grams": float(sp.remaining_grams),
        }
        for sp in spools
        if sp.remaining_grams < settings_row.low_spool_threshold_g
    ]

    inbox_rows = (
        await session.execute(
            select(WatcherInboxFile).where(
                WatcherInboxFile.status == WatcherInboxStatus.PENDING.value
            )
        )
    ).scalars().all()
    inbox = [
        {
            "id": str(r.id),
            "original_path": r.original_path,
            "parsed_meta": r.parsed_meta,
        }
        for r in inbox_rows
    ]

    return DashboardOut(
        cards=DashboardCards(
            receita=_q2(receita),
            despesa=_q2(despesa),
            lucro=_q2(lucro),
            margem_pct=_q2(margem),
            gasto_pessoal=_q2(gasto_pessoal),
            orcamentos_por_estado=estado_counts,
            taxa_conversao_pct=_q2(conversion),
            estoque=CardEstoque(
                total_grams=_q2(Decimal(total_grams)),
                estimated_value=_q2(Decimal(estimated_value)),
            ),
        ),
        charts=DashboardCharts(
            receita_vs_despesa=[
                {
                    "period": bk,
                    "receita": float(_q2(v["receita"])),
                    "despesa": float(_q2(v["despesa"])),
                }
                for bk, v in sorted(rev_exp_buckets.items())
            ],
            funil={
                "orcado": orcado_n,
                "aprovado": estado_counts.get(QuoteStatus.APROVADO.value, 0),
                "produzido": estado_counts.get(QuoteStatus.PRODUZIDO.value, 0),
                "entregue": estado_counts.get(QuoteStatus.ENTREGUE.value, 0),
            },
            despesa_categorias={
                k: float(_q2(v)) for k, v in cat_totals.items()
            },
            orcado_vs_real=sorted(
                orcado_vs_real_rows,
                key=lambda r: abs(r["variancia_pct"]),
                reverse=True,
            ),
        ),
        lists=DashboardLists(
            ultimos_orcamentos=ultimos,
            parados=parados,
            spools_baixos=low_spools,
            inbox=inbox,
        ),
    )
