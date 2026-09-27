from decimal import Decimal
from backend.core.pricing.labor import labor_cost, LaborLine
from backend.core.pricing.failure import apply_failure
from backend.core.pricing.quote import (
    FilamentLine,
    compute_item_cost,
    compute_quote_total,
    ItemInput,
    ServiceLine,
)


def test_labor_cost_minute():
    line = LaborLine(unit="min", quantity=Decimal("15"), rate=Decimal("1.20"))
    assert labor_cost([line]) == Decimal("18.00")


def test_apply_failure():
    base = Decimal("100")
    assert apply_failure(base, failure_pct=Decimal("5")) == Decimal("105.00")


def test_compute_quote_total_commercial():
    item = ItemInput(
        filaments=(FilamentLine(grams=Decimal("50"), price_per_kg=Decimal("100")),),
        time_s=3600, power_w=Decimal("150"), kwh_price=Decimal("1.0"),
        depreciation_per_hour=Decimal("2.0"), failure_pct=Decimal("0"),
        quantity=1,
    )
    services = [ServiceLine(quantity=Decimal("10"), rate=Decimal("1.0"), is_material=False)]
    total = compute_quote_total(items=[item], services=services, markup_pct=Decimal("50"), min_charge=Decimal("0"))
    # filament: 50g * 100/1000 = 5; energy: 1h*150W*1.0 = 0.15; deprec: 2.0; failure: 0%; labor: 10
    # cost = 5 + 0.15 + 2.0 + 10 = 17.15 → markup 50% → 25.725
    assert round(total, 2) == Decimal("25.73")


def test_min_charge_floor():
    item = ItemInput(filaments=(FilamentLine(grams=Decimal("1"), price_per_kg=Decimal("100")),),
                     time_s=60, power_w=Decimal("100"), kwh_price=Decimal("1.0"),
                     depreciation_per_hour=Decimal("0"), failure_pct=Decimal("0"), quantity=1)
    total = compute_quote_total(items=[item], services=[], markup_pct=Decimal("0"), min_charge=Decimal("50"))
    assert total == Decimal("50.00")


def test_custo_soma_os_filamentos_e_conta_o_tempo_uma_vez():
    """A armadilha central do multicor.

    Gramas somam por linha de cor; time_s NÃO. O gcode descreve a impressão da
    peça inteira, com todas as suas cores — somar o tempo por linha
    multiplicaria energia e depreciação pelo número de cores.

    Duas cores E quantidade 3 de propósito: com uma cor não dá para distinguir
    as duas regras, e com quantidade 1 o ×quantity fica invisível.
    """
    from backend.core.pricing.cost import depreciation_cost, energy_cost, filament_cost

    time_s = 3600
    qty = 3
    power_w = Decimal("150")
    kwh = Decimal("0.95")
    dep_h = Decimal("1.50")

    item = ItemInput(
        filaments=(
            FilamentLine(grams=Decimal("12"), price_per_kg=Decimal("100")),
            FilamentLine(grams=Decimal("8"), price_per_kg=Decimal("250")),  # preço diferente
        ),
        time_s=time_s,
        power_w=power_w,
        kwh_price=kwh,
        depreciation_per_hour=dep_h,
        failure_pct=Decimal("0"),
        quantity=qty,
    )

    fil_esperado = (filament_cost(Decimal("12"), Decimal("100"))
                    + filament_cost(Decimal("8"), Decimal("250")))
    en_esperado = energy_cost(time_s, power_w, kwh)        # UMA vez, não duas
    dep_esperado = depreciation_cost(time_s, dep_h)        # UMA vez, não duas
    # apply_failure arredonda a 2 casas por item ANTES de multiplicar pela
    # quantidade — é assim que compute_item_cost já se comporta hoje (mesma
    # ordem antes e depois desta task). Reaplicar aqui em vez de somar direto
    # e multiplicar por qty evita um falso positivo de arredondamento que não
    # tem nada a ver com a regra grams-soma/time-uma-vez que este teste cobre.
    esperado = apply_failure(fil_esperado + en_esperado + dep_esperado, Decimal("0")) * Decimal(qty)

    assert compute_item_cost(item) == esperado


def test_precos_diferentes_por_linha_nao_viram_media():
    """Gramas DIFERENTES de propósito.

    Com gramas iguais este teste não valeria nada: 10 g a R$50 + 10 g a R$450
    soma R$5,00, e 20 g ao preço médio de R$250 também dá R$5,00 — a asserção
    passaria mesmo se alguém "simplificasse" usando a média. Medido:
    soma=5.00, média=5.00.

    Com 20 g a R$50 + 5 g a R$450 a soma é R$3,25 e a média daria R$6,25, então
    a asserção distingue as duas implementações. É o mesmo cuidado que faltou
    nos dois testes que deixaram passar o bug do PR #32 usando quantity=1.
    """
    base = dict(time_s=0, power_w=Decimal("0"), kwh_price=Decimal("0"),
                depreciation_per_hour=Decimal("0"), failure_pct=Decimal("0"), quantity=1)
    total = compute_item_cost(ItemInput(filaments=(
        FilamentLine(Decimal("20"), Decimal("50")),
        FilamentLine(Decimal("5"), Decimal("450")),
    ), **base))
    assert total == Decimal("1.00") + Decimal("2.25")   # 3,25 — pela média daria 6,25


def test_item_de_uma_linha_custa_o_mesmo_que_antes():
    """Regressão: a troca de grams/price_per_kg por filaments não muda o
    número de um item de uma cor."""
    item = ItemInput(
        filaments=(FilamentLine(grams=Decimal("60"), price_per_kg=Decimal("120")),),
        time_s=4 * 3600, power_w=Decimal("150"), kwh_price=Decimal("0.95"),
        depreciation_per_hour=Decimal("1.50"), failure_pct=Decimal("0"), quantity=4,
    )
    assert compute_item_cost(item) == Decimal("55.08")
