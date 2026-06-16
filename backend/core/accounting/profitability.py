from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.accounting.dre import sale_cpv
from backend.core.pricing.cost import grams_from_meters, filament_cost
from backend.infra.db.models import Client, MaterialVersion, QuoteItem, Sale

_DIAMETER_MM = Decimal("1.75")


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


def _rows(agg: dict[str, dict]) -> list[dict]:
    out = []
    for label, v in agg.items():
        receita, custo = v["receita"], v["custo"]
        margem = receita - custo
        pct = (margem / receita * Decimal(100)) if receita > 0 else Decimal(0)
        out.append({"label": label, "receita": _q2(receita), "custo": _q2(custo),
                    "margem": _q2(margem), "margem_pct": _q2(pct)})
    out.sort(key=lambda r: r["margem"], reverse=True)
    return out


async def compute_profitability(session: AsyncSession, period_from: date, period_to: date) -> dict:
    sales = (
        await session.execute(
            select(Sale).where(
                Sale.is_sold.is_(True), Sale.is_stale.is_(False),
                Sale.sold_at.is_not(None),
                Sale.sold_at >= period_from, Sale.sold_at <= period_to,
            )
        )
    ).scalars().all()

    by_client: dict[str, dict] = {}
    by_material: dict[str, dict] = {}

    for sale in sales:
        receita = sale.confirmed_revenue or Decimal(0)
        custo = sale_cpv(sale) + sale.variable_costs

        cname = "—"
        if sale.client_id:
            c = await session.get(Client, sale.client_id)
            cname = c.name if c else "—"
        slot = by_client.setdefault(cname, {"receita": Decimal(0), "custo": Decimal(0)})
        slot["receita"] += receita; slot["custo"] += custo

        items = (await session.execute(
            select(QuoteItem).where(QuoteItem.quote_id == sale.quote_id))).scalars().all()
        shares: list[tuple[str, Decimal]] = []
        for it in items:
            mt = "—"; fcost = Decimal(0)
            if it.material_version_id:
                mv = await session.get(MaterialVersion, it.material_version_id)
                if mv:
                    mt = mv.material_type
                    grams = grams_from_meters(float(it.gcode_meta.get("filament_m", 0) or 0),
                                              mv.density_g_cm3, _DIAMETER_MM) * Decimal(it.quantity)
                    fcost = filament_cost(grams, mv.price_per_kg_ref)
            shares.append((mt, fcost))
        total_share = sum((c for _, c in shares), Decimal(0))
        if total_share <= 0:
            slot = by_material.setdefault("—", {"receita": Decimal(0), "custo": Decimal(0)})
            slot["receita"] += receita; slot["custo"] += custo
        else:
            for mt, fcost in shares:
                frac = fcost / total_share
                slot = by_material.setdefault(mt, {"receita": Decimal(0), "custo": Decimal(0)})
                slot["receita"] += receita * frac; slot["custo"] += custo * frac

    return {"by_client": _rows(by_client), "by_material": _rows(by_material)}
