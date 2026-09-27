from decimal import Decimal

import pytest

from backend.core.accounting.cost import apply_markup, compute_quote_costs
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialConsumption, MaterialVersion, Quote, QuoteItem, QuoteItemFilament, Settings, Spool,
    User,
)
from backend.core.models import QuoteKind, QuoteStatus
from datetime import datetime, timezone


def test_apply_markup_min_charge():
    # 100 + 50% = 150, acima do min_charge 80
    assert apply_markup(Decimal("100"), Decimal("50"), Decimal("80")) == Decimal("150")
    # 100 + 0% = 100, abaixo do min_charge 200 -> usa min
    assert apply_markup(Decimal("100"), Decimal("0"), Decimal("200")) == Decimal("200")


@pytest.mark.asyncio
async def test_compute_quote_costs_components():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="cost@t.com", password_hash="x")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("1.00"),
                                          printer_power_w=Decimal("100"),
                                          printer_depreciation_per_hour=Decimal("0"),
                                          printer_maintenance_per_hour=Decimal("0")))
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        # 10 m de filamento, 3600 s de impressão
        item = QuoteItem(quote_id=q.id, name="peça", gcode_meta={"filament_m": 10, "time_s": 3600},
                         material_version_id=mv.id, quantity=1)
        spool = Spool(material_type="PLA", purchased_at=datetime.now(timezone.utc),
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("900"))
        s.add_all([item, spool]); await s.commit()
        s.add(QuoteItemFilament(quote_item_id=item.id, material_version_id=mv.id,
                                grams_unit=None, position=1))
        await s.commit()
        # consumo real: 25 g a R$0,10/g = R$2,50
        cons = MaterialConsumption(quote_item_id=item.id, spool_id=spool.id,
                                   grams_used=Decimal("25"), unit_cost_snapshot=Decimal("0.10"))
        s.add(cons); await s.commit()

        costs = await compute_quote_costs(s, q, settings)
        # energia: 100W * 1h / 1000 * R$1 = R$0,10
        assert costs.energy == Decimal("0.10")
        assert costs.real_filament == Decimal("2.50")
        assert costs.cpv == costs.real_filament + costs.energy + costs.depreciation + costs.services


@pytest.mark.asyncio
async def test_compute_quote_costs_honors_filament_g():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="grams@t.com", password_hash="x")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("0"),
                                          printer_power_w=Decimal("0"),
                                          printer_depreciation_per_hour=Decimal("0"),
                                          printer_maintenance_per_hour=Decimal("0")))
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        item = QuoteItem(quote_id=q.id, name="p",
                         gcode_meta={"filament_m": 10, "time_s": 0, "filament_g": 50},
                         material_version_id=mv.id, quantity=1)
        s.add(item); await s.commit()
        s.add(QuoteItemFilament(quote_item_id=item.id, material_version_id=mv.id,
                                grams_unit=None, position=1))
        await s.commit()

        costs = await compute_quote_costs(s, q, settings)
        assert costs.catalog_filament == Decimal("5.00")


@pytest.mark.asyncio
async def test_cpv_escala_energia_e_depreciacao_com_a_quantidade():
    """Regressão: com quantity>1, energia e depreciação escalavam? Não escalavam.

    Os dois testes acima usam quantity=1, onde ×1 esconde a diferença. Este usa
    4 cópias justamente para que a asserção possa falhar: se alguém voltar a
    somar `energy_cost(time_s, ...)` sem multiplicar pela quantidade, o valor
    esperado cai a um quarto e o teste quebra.

    A referência é o caminho de pricing (`compute_item_cost`), que multiplica o
    custo inteiro — filamento, energia, depreciação — por `quantity`. Os dois
    caminhos precisam concordar sobre o mesmo orçamento: um cobra do cliente, o
    outro vira CPV no DRE.
    """
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="qty@t.com", password_hash="x")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("1.00"),
                                         printer_power_w=Decimal("100"),
                                         printer_depreciation_per_hour=Decimal("2.00"),
                                         printer_maintenance_per_hour=Decimal("0")))
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        # 1h de impressão por peça, 4 cópias.
        item = QuoteItem(quote_id=q.id, name="peça", gcode_meta={"filament_m": 10, "time_s": 3600},
                         material_version_id=mv.id, quantity=4)
        s.add(item); await s.commit()
        s.add(QuoteItemFilament(quote_item_id=item.id, material_version_id=mv.id,
                                grams_unit=None, position=1))
        await s.commit()

        costs = await compute_quote_costs(s, q, settings)

        # energia por peça: 100W × 1h ÷ 1000 × R$1,00 = R$0,10  ->  ×4 = R$0,40
        assert costs.energy == Decimal("0.40"), (
            f"energia nao escalou com a quantidade: {costs.energy} (esperado 0.40)"
        )
        # depreciação por peça: 1h × R$2,00 = R$2,00  ->  ×4 = R$8,00
        assert costs.depreciation == Decimal("8.00"), (
            f"depreciacao nao escalou com a quantidade: {costs.depreciation} (esperado 8.00)"
        )


@pytest.mark.asyncio
async def test_cpv_concorda_com_o_pricing_no_mesmo_item():
    """Os dois motores de custo não podem divergir sobre o mesmo item.

    `pricing/quote.py` decide o que o cliente paga; `accounting/cost.py` decide
    o CPV que vai pro DRE. Divergência entre eles é margem fantasma. Este teste
    compara os dois diretamente, com quantidade > 1 para que a assimetria de
    escala apareça.

    Compara só filamento de catálogo + energia + depreciação, com
    `failure_pct` e `printer_maintenance_per_hour` ZERADOS nos dois motores —
    não porque o contábil deixe de aplicar esses termos (ele aplica: ambos
    entram em `orcado_itens`/`cost_orcado`, igual ao pricing, desde que a task
    de refugo/manutenção fechou essa lacuna). É para isolar a concordância dos
    três termos de base sem arrastar a lógica de provisão de falha e
    manutenção para esta asserção — essa concordância já tem teste próprio
    (`test_total_da_venda_bate_com_o_total_do_pdf`, com os dois NÃO-zero) e o
    isolamento de `cpv` (que nunca leva manutenção nem provisão) tem o dele
    (`test_cpv_nao_ganha_manutencao_nem_provisao_de_falha`).
    """
    from backend.core.pricing.quote import FilamentLine, ItemInput, compute_item_cost

    async with session_module.SessionFactory() as s:
        user = User(name="u", email="cmp@t.com", password_hash="x")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("0.95"),
                                         printer_power_w=Decimal("150"),
                                         printer_depreciation_per_hour=Decimal("1.50"),
                                         printer_maintenance_per_hour=Decimal("0")))
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        item = QuoteItem(quote_id=q.id, name="peça",
                         gcode_meta={"filament_m": 20, "time_s": 4 * 3600, "filament_g": 60},
                         material_version_id=mv.id, quantity=4)
        s.add(item); await s.commit()
        s.add(QuoteItemFilament(quote_item_id=item.id, material_version_id=mv.id,
                                grams_unit=None, position=1))
        await s.commit()

        costs = await compute_quote_costs(s, q, settings)
        contabil = costs.catalog_filament + costs.energy + costs.depreciation

        pricing = compute_item_cost(ItemInput(
            filaments=(FilamentLine(grams=Decimal("60"), price_per_kg=Decimal("100")),),
            time_s=4 * 3600,
            power_w=Decimal("150"), kwh_price=Decimal("0.95"),
            depreciation_per_hour=Decimal("1.50"), failure_pct=Decimal("0"), quantity=4,
        ))

        assert contabil == pricing, (
            f"contabil ({contabil}) divergiu do pricing ({pricing}) no mesmo item"
        )


@pytest.mark.asyncio
async def test_catalog_filament_soma_as_cores_e_energia_conta_uma_vez():
    """Item bicolor: filamento de catálogo soma as duas linhas; energia e
    depreciação continuam contando o time_s uma vez (× quantidade).

    Duas cores E quantidade 3 — de propósito **diferentes** entre si. Com
    quantidade igual ao número de cores (era 2 e 2), "energia por peça × qty"
    e "energia por peça × número de cores" dão o mesmíssimo número, e a
    confusão que este teste existe para pegar passaria despercebida. Com
    quantidade 3 as duas leituras divergem (0,30 vs 0,20 / 6,00 vs 4,00), e só
    a leitura certa (× quantidade) bate.
    """
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="multicor@t.com", password_hash="x")
        mv_a = MaterialVersion(material_type="PLA", name="PLA Preto", color="Preto",
                               density_g_cm3=Decimal("1.24"), price_per_kg_ref=Decimal("100"))
        mv_b = MaterialVersion(material_type="PLA", name="PLA Ouro", color="Ouro",
                               density_g_cm3=Decimal("1.24"), price_per_kg_ref=Decimal("300"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("1.00"),
                                         printer_power_w=Decimal("100"),
                                         printer_depreciation_per_hour=Decimal("2.00"),
                                         printer_maintenance_per_hour=Decimal("0")))
        s.add_all([user, mv_a, mv_b]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        item = QuoteItem(quote_id=q.id, name="bicolor",
                         gcode_meta={"filament_m": 10, "time_s": 3600},
                         material_version_id=mv_a.id, quantity=3)
        s.add(item); await s.commit()
        s.add_all([
            QuoteItemFilament(quote_item_id=item.id, material_version_id=mv_a.id,
                              grams_unit=Decimal("30"), position=1),
            QuoteItemFilament(quote_item_id=item.id, material_version_id=mv_b.id,
                              grams_unit=Decimal("10"), position=2),
        ])
        await s.commit()

        costs = await compute_quote_costs(s, q, settings)

        # filamento: (30g × R$100/kg) + (10g × R$300/kg) = 3,00 + 3,00 = 6,00, × 3 cópias
        assert costs.catalog_filament == Decimal("18.00"), (
            f"catalog_filament {costs.catalog_filament} — conferir se as duas linhas somaram"
        )
        # energia: 100W × 1h ÷ 1000 × R$1 = 0,10 → × 3 cópias = 0,30. NÃO × 2 cores (0,20).
        assert costs.energy == Decimal("0.30"), (
            f"energia {costs.energy} — se deu 0.20, foi × número de cores (2), não × quantidade (3)"
        )
        # depreciação: 1h × R$2,00 = 2,00 → × 3 cópias = 6,00. NÃO × 2 cores (4,00).
        assert costs.depreciation == Decimal("6.00"), (
            f"depreciacao {costs.depreciation} — se deu 4.00, foi × número de cores (2), não × quantidade (3)"
        )


@pytest.mark.asyncio
async def test_linha_nula_em_item_multicor_mantem_os_20_por_cento():
    """A linha de `grams_unit NULL` segue a regra de refugo de HOJE.

    É o que garante que a migração 0034 não mexe em dinheiro. Não dá para
    comparar com um "antes" calculado pelo código novo: sem linhas, o laço pula
    o item e devolve zero, e a comparação ficaria vazia. Então a asserção fixa o
    valor esperado montado com as primitivas antigas, deixando explícitos os
    dois pontos que importam — os 20% de `is_multi_color` (não os 2% de cor
    única) e o × quantidade.

    Falha se alguém "simplificar" a regra de refugo para depender da contagem de
    linhas, que é a mudança tentadora e errada.
    """
    from backend.core.pricing.cost import filament_cost
    from backend.core.quote_service import effective_grams_per_unit

    async with session_module.SessionFactory() as s:
        user = User(name="u", email="refugonulo@t.com", password_hash="x")
        mv = MaterialVersion(material_type="PLA", name="PLA", color="Preto",
                             density_g_cm3=Decimal("1.24"), price_per_kg_ref=Decimal("100"),
                             single_color_waste_pct=Decimal("2"),
                             multi_color_waste_pct=Decimal("20"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("0"),
                                         printer_power_w=Decimal("0"),
                                         printer_depreciation_per_hour=Decimal("0"),
                                         printer_maintenance_per_hour=Decimal("0")))
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        # is_multi_color=True é o caso em que a regra poderia "simplificar" errado
        item = QuoteItem(quote_id=q.id, name="antigo",
                         gcode_meta={"filament_m": 10, "time_s": 3600},
                         material_version_id=mv.id, quantity=2, is_multi_color=True)
        s.add(item); await s.commit()
        s.add(QuoteItemFilament(quote_item_id=item.id, material_version_id=mv.id,
                                grams_unit=None, position=1))
        await s.commit()

        costs = await compute_quote_costs(s, q, settings)

    gramas_por_peca = effective_grams_per_unit(
        10, None, Decimal("1.24"), Decimal("1.75"), Decimal("20")
    )
    esperado = filament_cost(gramas_por_peca * Decimal(2), Decimal("100"))
    assert costs.catalog_filament == esperado, (
        f"catalog_filament {costs.catalog_filament} != {esperado} — se deu menos, "
        "a linha NULL usou single_color_waste_pct (2%) em vez dos 20% de "
        "is_multi_color, e o custo do histórico mudou"
    )


@pytest.mark.asyncio
async def test_total_da_venda_bate_com_o_total_do_pdf():
    """Os dois motores precisam concordar sobre o TOTAL, não só sobre as parcelas.

    Achado durante a execução do plano, e é dinheiro: a tela do orçamento e o PDF
    usam `compute_quote_total` (pricing), que aplica o refugo do material.
    `sale.quote_total` vem de `apply_markup(cost_orcado)` (contábil), que passava
    refugo ZERO. Medido: o total da venda ficava 1,0% abaixo do PDF num item de uma
    cor (refugo 2%) e 9,4% abaixo num multicor (refugo 20%) — o cliente recebia um
    PDF com um número e o sistema gravava outro.

    Usar `waste_for_line` nesta task fecha a diferença. Este teste é o que impede
    de reabrir.

    `quantity=3`, não 1 (achado do review): em quantity=1, `apply_failure(base) ×
    1` é indistinguível de aplicar a provisão sobre o agregado — a regra de
    ordem que esta task existe para garantir não conseguia derrubar este teste.
    Com >1 cópia, as duas ordens dão números diferentes, e só a ordem certa
    (por peça, depois × quantity) bate com `compute_quote_total`.

    Também acrescenta um serviço (achado do review): sem nenhum `QuoteService`,
    "serviços ficam FORA da provisão de falha" não era exercitado por nenhum
    teste da suíte. Os dois motores incluem o mesmo serviço fora da falha.
    """
    from backend.core.accounting.cost import apply_markup
    from backend.core.models import ServiceKind, ServiceUnit
    from backend.core.pricing.quote import ServiceLine, compute_quote_total
    from backend.core.quotes.filaments import grams_for_line, waste_for_line
    from backend.core.pricing.quote import FilamentLine, ItemInput
    from backend.infra.db.models import QuoteService, Service

    async with session_module.SessionFactory() as s:
        user = User(name="u", email="totalbate@t.com", password_hash="x")
        # refugo de uma cor em 2%, que é o default do cadastro
        mv = MaterialVersion(material_type="PLA", name="PLA", color="Preto",
                             density_g_cm3=Decimal("1.24"), price_per_kg_ref=Decimal("120"),
                             single_color_waste_pct=Decimal("2"),
                             multi_color_waste_pct=Decimal("20"))
        # manutenção e falha NÃO-ZERO de propósito. Com os dois em zero este teste
        # verificaria a concordância justamente com os termos que divergem anulados —
        # passaria provando nada. Medido: com manutenção 0,50/h a divergência é 12,7%,
        # e com falha 8% em cima vai a 19,1%.
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("0.95"),
                                         printer_power_w=Decimal("150"),
                                         printer_depreciation_per_hour=Decimal("1.50"),
                                         printer_maintenance_per_hour=Decimal("0.50")))
        mv.failure_rate_pct = Decimal("8")
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("100"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        item = QuoteItem(quote_id=q.id, name="peça",
                         gcode_meta={"filament_m": 20, "time_s": 4 * 3600},
                         material_version_id=mv.id, quantity=3)
        s.add(item); await s.commit()
        s.add(QuoteItemFilament(quote_item_id=item.id, material_version_id=mv.id,
                                grams_unit=None, position=1))
        svc = Service(name="Montagem", unit=ServiceUnit.MINUTE,
                      default_rate=Decimal("15.00"), kind=ServiceKind.OTHER)
        s.add(svc); await s.flush()
        s.add(QuoteService(quote_id=q.id, service_id=svc.id, quantity=Decimal("1"),
                           rate=Decimal("15.00")))
        await s.commit()

        costs = await compute_quote_costs(s, q, settings)
        total_contabil = apply_markup(costs.cost_orcado, q.markup_pct, q.min_charge)

        # o mesmo item pelo motor de pricing, que é o que a tela e o PDF mostram
        waste = waste_for_line(None, False, mv.single_color_waste_pct, mv.multi_color_waste_pct)
        gramas = grams_for_line(None, item.gcode_meta, mv.density_g_cm3, waste)
        total_pdf = compute_quote_total(
            [ItemInput(
                filaments=(FilamentLine(grams=gramas, price_per_kg=mv.price_per_kg_ref),),
                time_s=4 * 3600, power_w=settings.printer_power_w,
                kwh_price=settings.energy_kwh_price,
                depreciation_per_hour=settings.printer_depreciation_per_hour,
                failure_pct=mv.failure_rate_pct, quantity=3,
                maintenance_per_hour=settings.printer_maintenance_per_hour,
            )],
            [ServiceLine(quantity=Decimal("1"), rate=Decimal("15.00"), is_material=False)],
            q.markup_pct, q.min_charge,
        )

    assert total_contabil.quantize(Decimal("0.01")) == total_pdf.quantize(Decimal("0.01")), (
        f"contábil {total_contabil} != PDF {total_pdf} — se o contábil ficou MENOR, "
        "ele voltou a passar refugo zero e sale.quote_total divergiu do PDF que o "
        "cliente recebeu"
    )


@pytest.mark.asyncio
async def test_cpv_nao_ganha_manutencao_nem_provisao_de_falha():
    """`cpv` é o custo REALIZADO — nunca ganha manutenção nem provisão de falha,
    mesmo com os dois configurados e diferentes de zero.

    Achado do review: o único outro teste que toca `cpv`
    (`test_compute_quote_costs_components`) recompõe a asserção a partir dos
    PRÓPRIOS campos da property (`costs.cpv == costs.real_filament +
    costs.energy + costs.depreciation + costs.services`) — se alguém somar
    `+ self.maintenance` ou uma provisão de falha em `QuoteCosts.cpv`, essa
    asserção passa de qualquer jeito, e é a sétima vez que um teste deste
    trabalho não discrimina o termo que deveria. Este teste usa
    `printer_maintenance_per_hour` e `failure_rate_pct` NÃO-ZERO e compara com
    um número literal calculado à mão, para que a adição de qualquer um dos
    dois termos a `cpv` quebre a asserção.

    Por que ficam de fora do realizado: uma provisão é dinheiro reservado para
    falhas que ainda não aconteceram. A peça deste teste foi produzida e teve
    consumo real registrado — não falhou — então cobrar a provisão no CPV
    contaria como gasto um dinheiro que não saiu do caixa. Manutenção é
    orçamento (rateio previsto por hora de máquina), não uma baixa realizada
    por item; por isso mora em `orcado_itens`/`cost_orcado`, não em `cpv`.
    """
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="cpvguard@t.com", password_hash="x")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"), failure_rate_pct=Decimal("10"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("1.00"),
                                          printer_power_w=Decimal("100"),
                                          printer_depreciation_per_hour=Decimal("2.00"),
                                          printer_maintenance_per_hour=Decimal("0.50")))
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        # 1h de impressão por peça, 2 cópias.
        item = QuoteItem(quote_id=q.id, name="peça", gcode_meta={"filament_m": 10, "time_s": 3600},
                         material_version_id=mv.id, quantity=2)
        spool = Spool(material_type="PLA", purchased_at=datetime.now(timezone.utc),
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("900"))
        s.add_all([item, spool]); await s.commit()
        s.add(QuoteItemFilament(quote_item_id=item.id, material_version_id=mv.id,
                                grams_unit=None, position=1))
        await s.commit()
        # consumo real: 25 g a R$0,10/g = R$2,50 (não escala por quantity — é o
        # que de fato saiu da bobina, já contando todas as cópias)
        cons = MaterialConsumption(quote_item_id=item.id, spool_id=spool.id,
                                   grams_used=Decimal("25"), unit_cost_snapshot=Decimal("0.10"))
        s.add(cons); await s.commit()

        costs = await compute_quote_costs(s, q, settings)

        # manutenção por peça: 1h × R$0,50 = 0,50 → × 2 cópias = 1,00 — existe,
        # mas fica em `maintenance`/`orcado_itens`, não em `cpv`.
        assert costs.maintenance == Decimal("1.00"), (
            f"maintenance {costs.maintenance} — deveria estar somando 1.00, "
            "senão este teste não prova que a manutenção existe pra vazar"
        )
        # cpv = real_filament(2,50) + energia(0,10×2=0,20) + depreciação(2,00×2=4,00)
        # + serviços(0) = 6,70. SEM os 1,00 de manutenção e SEM a provisão de
        # falha de 10% (que fica em `orcado_itens`, aplicada por peça).
        assert costs.cpv == Decimal("6.70"), (
            f"cpv {costs.cpv} != 6.70 — se deu 7.70, a manutenção vazou pro cpv; "
            "qualquer outro valor, a provisão de falha vazou"
        )
