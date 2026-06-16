from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.pricing.cost import depreciation_cost, energy_cost, filament_cost
from backend.infra.db.models import (
    MaterialConsumption, MaterialVersion, QuoteItem, QuoteService, Settings,
)

_DIAMETER_MM = Decimal("1.75")
_PI = Decimal("3.14159265358979323846")


@dataclass
class QuoteCosts:
    catalog_filament: Decimal  # filamento de catálogo (gcode × densidade × preço-ref)
    real_filament: Decimal     # filamento real consumido (snapshots)
    energy: Decimal
    depreciation: Decimal
    services: Decimal

    @property
    def cost_orcado(self) -> Decimal:
        return self.catalog_filament + self.energy + self.depreciation + self.services

    @property
    def cpv(self) -> Decimal:
        return self.real_filament + self.energy + self.depreciation + self.services


def apply_markup(cost_orcado: Decimal, markup_pct: Decimal, min_charge: Decimal) -> Decimal:
    """Total do orçamento: custo × (1 + markup), respeitando o piso min_charge.

    Sem quantize — mantém paridade exata com o dashboard atual."""
    total = cost_orcado * (Decimal(100) + markup_pct) / Decimal(100)
    if total < min_charge:
        total = min_charge
    return total


def load_settings_row(settings_row: Settings | None) -> Settings:
    """Default em memória quando ainda não há linha de Settings (espelha o dashboard)."""
    if settings_row is not None:
        return settings_row
    return Settings(
        id=1,
        energy_kwh_price=Decimal("0.95"),
        printer_power_w=Decimal("150"),
        printer_depreciation_per_hour=Decimal("0"),
        stalled_quote_alert_days=7,
        low_spool_threshold_g=Decimal("100"),
    )


async def compute_quote_costs(session: AsyncSession, quote, settings_row: Settings) -> QuoteCosts:
    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == quote.id))
    ).scalars().all()
    services = (
        await session.execute(select(QuoteService).where(QuoteService.quote_id == quote.id))
    ).scalars().all()

    catalog_filament = Decimal(0)
    real_filament = Decimal(0)
    energy = Decimal(0)
    depreciation = Decimal(0)

    for it in items:
        mv = await session.get(MaterialVersion, it.material_version_id)
        if mv is None:
            continue
        filament_m = Decimal(str(it.gcode_meta.get("filament_m", 0)))
        time_s = float(it.gcode_meta.get("time_s", 0))
        area = (_PI / Decimal(4)) * (_DIAMETER_MM ** 2)
        grams_per_m = area * mv.density_g_cm3
        grams = filament_m * grams_per_m * Decimal(it.quantity)
        catalog_filament += filament_cost(grams, mv.price_per_kg_ref)
        energy += energy_cost(time_s, settings_row.printer_power_w, settings_row.energy_kwh_price)
        dep_rate = it.depreciation_rate_override or settings_row.printer_depreciation_per_hour
        depreciation += depreciation_cost(time_s, dep_rate)

        cons = (
            await session.execute(
                select(MaterialConsumption).where(MaterialConsumption.quote_item_id == it.id)
            )
        ).scalars().all()
        for c in cons:
            real_filament += c.grams_used * c.unit_cost_snapshot

    services_cost = sum((sv.quantity * sv.rate for sv in services), Decimal(0))
    return QuoteCosts(
        catalog_filament=catalog_filament,
        real_filament=real_filament,
        energy=energy,
        depreciation=depreciation,
        services=services_cost,
    )
