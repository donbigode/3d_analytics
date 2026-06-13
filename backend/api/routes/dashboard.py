from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
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
    MaterialConsumption,
    MaterialVersion,
    Quote,
    QuoteItem,
    QuoteService,
    Settings,
    Spool,
    User,
    WatcherInboxFile,
)

router = APIRouter()


_DIAMETER_MM = Decimal("1.75")
_PI = Decimal("3.14159265358979323846")


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
    settings_row = await session.get(Settings, 1)
    if settings_row is None:
        settings_row = Settings(
            id=1,
            energy_kwh_price=Decimal("0.95"),
            printer_power_w=Decimal("150"),
            printer_depreciation_per_hour=Decimal("0"),
            stalled_quote_alert_days=7,
            low_spool_threshold_g=Decimal("100"),
        )

    now = datetime.now(timezone.utc)
    period_from = from_ or (now - timedelta(days=30))
    period_to = to or now

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
    rev_exp_buckets: dict[str, dict[str, Decimal]] = {}
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

        items = (
            await session.execute(
                select(QuoteItem).where(QuoteItem.quote_id == q.id)
            )
        ).scalars().all()
        services = (
            await session.execute(
                select(QuoteService).where(QuoteService.quote_id == q.id)
            )
        ).scalars().all()

        item_grams_cost = Decimal(0)
        item_energy = Decimal(0)
        item_dep = Decimal(0)

        for it in items:
            mv = await session.get(MaterialVersion, it.material_version_id)
            if mv is None:
                continue
            filament_m = Decimal(str(it.gcode_meta.get("filament_m", 0)))
            time_s = Decimal(str(it.gcode_meta.get("time_s", 0)))
            area = (_PI / Decimal(4)) * (_DIAMETER_MM ** 2)  # mm^2
            grams_per_m = area * mv.density_g_cm3  # g per meter
            grams = filament_m * grams_per_m * Decimal(it.quantity)
            item_grams_cost += (grams / Decimal(1000)) * mv.price_per_kg_ref
            hours = time_s / Decimal(3600)
            item_energy += (
                (settings_row.printer_power_w * hours / Decimal(1000))
                * settings_row.energy_kwh_price
            )
            dep_rate = it.depreciation_rate_override or settings_row.printer_depreciation_per_hour
            item_dep += hours * dep_rate

        services_cost = sum((s.quantity * s.rate for s in services), Decimal(0))
        cost_orcado = item_grams_cost + item_energy + item_dep + services_cost
        total = cost_orcado * (Decimal(100) + q.markup_pct) / Decimal(100)
        if total < q.min_charge:
            total = q.min_charge

        # Real filament — used by despesa, gasto_pessoal, G6 and category chart.
        async def _real_filament_for(items_list) -> Decimal:
            total = Decimal(0)
            for it_inner in items_list:
                cons = (
                    await session.execute(
                        select(MaterialConsumption).where(
                            MaterialConsumption.quote_item_id == it_inner.id
                        )
                    )
                ).scalars().all()
                for c in cons:
                    total += c.grams_used * c.unit_cost_snapshot
            return total

        # Receita comercial: quotes commercial with status >= aprovado in period
        is_commercial_revenue = q.kind == QuoteKind.COMMERCIAL.value and status_key in (
            QuoteStatus.APROVADO.value,
            QuoteStatus.PRODUZIDO.value,
            QuoteStatus.ENTREGUE.value,
        )
        if is_commercial_revenue:
            receita += total
            # G1: bucket by approved_at (when the money "started flowing")
            ts = q.approved_at or q.created_at
            if ts is not None:
                bk = _bucket_key(ts, bucket_mode)
                slot = rev_exp_buckets.setdefault(
                    bk, {"receita": Decimal(0), "despesa": Decimal(0)}
                )
                slot["receita"] += total

        # Despesa real: commercial produzido+ uses MaterialConsumption snapshots
        is_commercial_produced = q.kind == QuoteKind.COMMERCIAL.value and status_key in (
            QuoteStatus.PRODUZIDO.value,
            QuoteStatus.ENTREGUE.value,
        )
        if is_commercial_produced:
            real_filament = await _real_filament_for(items)
            real_cost = real_filament + item_energy + item_dep + services_cost
            despesa += real_cost

            # G3: despesa por categoria (real)
            cat_totals["filamento"] += real_filament
            cat_totals["energia"] += item_energy
            cat_totals["mao_obra"] += services_cost
            cat_totals["depreciacao"] += item_dep

            # G1: bucket by produced_at
            ts = q.produced_at or q.created_at
            if ts is not None:
                bk = _bucket_key(ts, bucket_mode)
                slot = rev_exp_buckets.setdefault(
                    bk, {"receita": Decimal(0), "despesa": Decimal(0)}
                )
                slot["despesa"] += real_cost

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
            real_filament_p = await _real_filament_for(items)
            real_cost_p = real_filament_p + item_energy + item_dep + services_cost
            gasto_pessoal += real_cost_p
            # Personal also contributes to category breakdown (it's still an expense)
            cat_totals["filamento"] += real_filament_p
            cat_totals["energia"] += item_energy
            cat_totals["mao_obra"] += services_cost
            cat_totals["depreciacao"] += item_dep

    lucro = receita - despesa
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
