from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.pricing.cost import (
    depreciation_cost, energy_cost, filament_cost, maintenance_cost,
)
from backend.core.pricing.failure import apply_failure
from backend.core.quotes.filaments import grams_for_line, waste_for_line
from backend.infra.db.models import (
    MaterialConsumption, MaterialVersion, QuoteItem, QuoteItemFilament, QuoteService, Settings,
)

@dataclass
class QuoteCosts:
    # Filamento de catálogo (gcode × densidade × preço-ref), só informativo —
    # derivado de fil_peca × qty, não soma em cost_orcado (quem alimenta o
    # preço é orcado_itens, via fil_peca).
    catalog_filament: Decimal
    real_filament: Decimal     # filamento real consumido (snapshots)
    energy: Decimal
    depreciation: Decimal
    maintenance: Decimal      # o pricing já cobrava, o contábil não somava
    services: Decimal
    orcado_itens: Decimal     # custo dos itens já com falha e manutenção

    @property
    def cost_orcado(self) -> Decimal:
        # Espelha compute_quote_total: itens (com provisão de falha) + serviços,
        # serviços FORA da falha.
        return self.orcado_itens + self.services

    @property
    def cpv(self) -> Decimal:
        # Realizado, não orçado: sem provisão de falha e sem manutenção. Provisão
        # de falha que não se concretizou não é dinheiro gasto.
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
    maintenance = Decimal(0)
    orcado_itens = Decimal(0)

    # Linhas de filamento de todos os itens numa query só.
    filaments_by_item: dict = {}
    if items:
        rows = (
            await session.execute(
                select(QuoteItemFilament, MaterialVersion)
                .join(MaterialVersion, MaterialVersion.id == QuoteItemFilament.material_version_id)
                .where(QuoteItemFilament.quote_item_id.in_([it.id for it in items]))
                .order_by(QuoteItemFilament.quote_item_id, QuoteItemFilament.position)
            )
        ).all()
        for fil, mv_line in rows:
            filaments_by_item.setdefault(fil.quote_item_id, []).append((fil, mv_line))

    for it in items:
        linhas = filaments_by_item.get(it.id, [])
        if not linhas:
            # Item sem linha = material não resolvido. Mesma semântica que o
            # `if mv is None: continue` de antes.
            continue
        time_s = float(it.gcode_meta.get("time_s", 0))
        qty = Decimal(it.quantity)

        # Gramas somam por linha de cor; time_s NÃO — ele descreve a impressão
        # da peça inteira, com todas as suas cores.
        fil_peca = Decimal(0)
        for fil, mv_line in linhas:
            waste = waste_for_line(
                fil.grams_unit, bool(it.is_multi_color),
                mv_line.single_color_waste_pct, mv_line.multi_color_waste_pct,
            )
            gramas_unit = grams_for_line(
                fil.grams_unit, it.gcode_meta, mv_line.density_g_cm3, waste
            )
            fil_peca += filament_cost(gramas_unit, mv_line.price_per_kg_ref)
        # `catalog_filament` é derivado de `fil_peca`, não um segundo
        # acumulador por linha: antes deste branch os dois só concordavam
        # porque `filament_cost` é linear e sem quantize (gramas_unit × qty ×
        # preço == (gramas_unit × preço) × qty, bit a bit). Um quantize
        # futuro em `filament_cost` faria os dois divergir em silêncio, com
        # só o campo coberto por teste (`catalog_filament`) mudando. Derivar
        # fecha essa fonte de divergência em vez de só documentá-la —
        # `catalog_filament` não alimenta `cost_orcado` (isso é `fil_peca` via
        # `orcado_itens`), é só o total de filamento de catálogo exibido à
        # parte.
        catalog_filament += fil_peca * qty

        # time_s e filament_m saem do MESMO cabeçalho de gcode e descrevem UMA
        # peça — a spec 2026-06-17-contabil-fato-itens declara `filament_m` como
        # "por peça", e `quantity` são cópias. Logo energia e depreciação também
        # escalam com a quantidade, como já fazem em pricing/quote.py
        # (compute_item_cost multiplica o custo inteiro por quantity).
        #
        # Antes daqui só as gramas escalavam, e o CPV de um item com 4 cópias
        # saía 35% abaixo do custo que o pricing cobrou do cliente — inflando a
        # margem do DRE e subestimando a perda operacional do uso pessoal. Os
        # dois testes que cobriam este laço usavam quantity=1, onde ×1 esconde
        # a diferença.
        en_peca = energy_cost(time_s, settings_row.printer_power_w, settings_row.energy_kwh_price)
        dep_rate = it.depreciation_rate_override or settings_row.printer_depreciation_per_hour
        dep_peca = depreciation_cost(time_s, dep_rate)
        maint_peca = maintenance_cost(time_s, settings_row.printer_maintenance_per_hour or Decimal(0))
        energy += en_peca * qty
        depreciation += dep_peca * qty
        maintenance += maint_peca * qty

        # Custo ORÇADO do item, espelhando compute_item_cost: provisão de falha
        # aplicada POR ITEM sobre a base por peça, e só depois × quantidade.
        # Aplicar a falha sobre o agregado daria número diferente, e serviços
        # ficam FORA dela — igual ao compute_quote_total.
        #
        # Decisão do Otavio (2026-09-26): ele quer que `sale.quote_total` bata com o
        # total do PDF. Medido antes: com manutenção 0,50/h a divergência era 12,7%,
        # e 19,1% somando falha de 8%. Batia hoje só porque os dois estão em zero.
        failure_pct = it.failure_rate_override or linhas[0][1].failure_rate_pct
        base_peca = fil_peca + en_peca + dep_peca + maint_peca
        orcado_itens += apply_failure(base_peca, failure_pct) * qty

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
        maintenance=maintenance,
        services=services_cost,
        orcado_itens=orcado_itens,
    )
