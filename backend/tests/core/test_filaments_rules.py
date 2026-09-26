"""Regras puras das linhas de filamento.

Sem banco de propósito: refugo e invariantes precisam de UM lugar só, e esse
lugar precisa ser testável em milissegundos.
"""
from dataclasses import dataclass
from decimal import Decimal

import pytest

from backend.core.quotes.filaments import (
    grams_for_line,
    renumber,
    validate_lines,
    waste_for_line,
)


@dataclass
class Linha:
    grams_unit: Decimal | None
    position: int


DENSIDADE = Decimal("1.24")
META = {"filament_m": 10, "time_s": 3600}


def test_gramas_digitadas_sao_valor_final_e_ignoram_refugo():
    # 20% de refugo não deve encostar num valor digitado (spec 3.3)
    assert grams_for_line(Decimal("12.34"), META, DENSIDADE, Decimal("20")) == Decimal("12.34")


def test_gramas_nulas_derivam_do_gcode_e_aplicam_refugo():
    sem_refugo = grams_for_line(None, META, DENSIDADE, Decimal("0"))
    com_refugo = grams_for_line(None, META, DENSIDADE, Decimal("20"))
    assert sem_refugo > 0
    assert com_refugo == sem_refugo * Decimal("120") / Decimal("100")


def test_gramas_nulas_respeitam_filament_g_do_gcode():
    # filament_g no gcode_meta já é valor final — mesmo contrato de hoje
    meta = {"filament_m": 10, "time_s": 3600, "filament_g": 50}
    assert grams_for_line(None, meta, DENSIDADE, Decimal("20")) == Decimal("50")


def test_refugo_de_linha_digitada_e_zero_mesmo_em_item_multicor():
    assert waste_for_line(Decimal("12.34"), True, Decimal("2"), Decimal("20")) == Decimal("0")


def test_refugo_de_linha_nula_segue_is_multi_color():
    # É isto que mantém o custo histórico idêntico após a 0034: item antigo
    # marcado is_multi_color continua com os 20%.
    assert waste_for_line(None, True, Decimal("2"), Decimal("20")) == Decimal("20")
    assert waste_for_line(None, False, Decimal("2"), Decimal("20")) == Decimal("2")


def test_lista_vazia_e_rejeitada():
    with pytest.raises(ValueError, match="pelo menos um filamento"):
        validate_lines([])


def test_duas_linhas_sem_gramas_sao_rejeitadas():
    # Sem esta regra as duas cairiam no ramo de derivação do gcode e o
    # filamento do item inteiro seria contado duas vezes.
    with pytest.raises(ValueError, match="gramas"):
        validate_lines([Linha(None, 1), Linha(None, 2)])


def test_duas_linhas_com_uma_sem_gramas_sao_rejeitadas():
    with pytest.raises(ValueError, match="gramas"):
        validate_lines([Linha(Decimal("10"), 1), Linha(None, 2)])


def test_duas_linhas_com_gramas_passam():
    validate_lines([Linha(Decimal("10"), 1), Linha(Decimal("5"), 2)])


def test_uma_linha_sem_gramas_passa():
    validate_lines([Linha(None, 1)])


def test_gramas_zero_sao_rejeitadas():
    # `None` já significa "não informado" (deriva do gcode); um `0` explícito
    # zeraria o custo da linha em silêncio, sem cair no fallback do gcode.
    with pytest.raises(ValueError, match="maiores que zero"):
        validate_lines([Linha(Decimal("0"), 1)])


def test_posicoes_nao_contiguas_sao_rejeitadas():
    with pytest.raises(ValueError, match="posição"):
        validate_lines([Linha(Decimal("10"), 1), Linha(Decimal("5"), 3)])


def test_posicoes_duplicadas_sao_rejeitadas():
    with pytest.raises(ValueError, match="posição"):
        validate_lines([Linha(Decimal("10"), 1), Linha(Decimal("5"), 1)])


def test_renumber_preserva_a_ordem():
    assert renumber([5, 1, 9]) == [1, 2, 3]
    assert renumber([]) == []
    assert renumber([1]) == [1]
