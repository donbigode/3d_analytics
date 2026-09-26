"""Regras das linhas de filamento de um item.

Puro, sem I/O. Existe para que a regra de refugo e as invariantes do conjunto
de linhas tenham um lugar só — espalhá-las entre o cálculo de pricing, o de
contábil e a validação da rota criaria três versões da mesma regra, que é como
o CPV e o pricing divergiram antes do PR #32.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Protocol, Sequence

from backend.core.quote_service import effective_grams_per_unit

_DIAMETER_MM = Decimal("1.75")


class LineShape(Protocol):
    """O mínimo que uma linha precisa expor para ser validada.

    Protocol em vez de uma classe concreta porque a validação roda tanto sobre o
    payload da API (Pydantic) quanto sobre as linhas já persistidas (ORM).
    """

    grams_unit: Decimal | None
    position: int


def waste_for_line(
    grams_unit: Decimal | None,
    is_multi_color: bool,
    single_pct: Decimal,
    multi_pct: Decimal,
) -> Decimal:
    """Refugo aplicável a uma linha.

    Gramas digitadas são valor final: o número é o que saiu da bobina, purga
    inclusa, exatamente como ``filament_g`` já se comporta. Refugo zero.

    Gramas nulas derivam do gcode e mantêm a regra de hoje, governada por
    ``is_multi_color``. Isto NÃO é concessão a código legado — é o que garante
    que o custo de todo orçamento histórico fique idêntico após a migração
    0034. Trocar para "tem mais de uma linha" reprecificaria itens antigos.
    """
    if grams_unit is not None:
        return Decimal(0)
    return (multi_pct if is_multi_color else single_pct) or Decimal(0)


def grams_for_line(
    grams_unit: Decimal | None,
    gcode_meta: dict,
    density: Decimal,
    waste_pct: Decimal,
    diameter_mm: Decimal = _DIAMETER_MM,
) -> Decimal:
    """Gramas **por peça** de uma linha.

    A multiplicação por ``quantity`` não acontece aqui: ela vive num lugar só,
    no cálculo de custo.
    """
    if grams_unit is not None:
        return grams_unit
    meters = float(gcode_meta.get("filament_m") or 0)
    raw_g = gcode_meta.get("filament_g")
    filament_g = float(raw_g) if raw_g not in (None, "") else None
    return effective_grams_per_unit(meters, filament_g, density, diameter_mm, waste_pct)


def validate_lines(lines: Sequence[LineShape]) -> None:
    """Invariantes do conjunto. Levanta ``ValueError`` na primeira violação.

    São do conjunto, não da linha — e é por isso que a API troca a lista
    inteira em vez de ter um endpoint por linha.
    """
    if not lines:
        raise ValueError("o item precisa de pelo menos um filamento")

    posicoes = [ln.position for ln in lines]
    if sorted(posicoes) != list(range(1, len(lines) + 1)):
        raise ValueError(
            f"posição das linhas precisa ser 1..{len(lines)} sem repetir; veio {sorted(posicoes)}"
        )

    if len(lines) > 1 and any(ln.grams_unit is None for ln in lines):
        raise ValueError(
            "item com mais de um filamento precisa das gramas de cada linha — "
            "não há como dividir o filamento do gcode entre as cores"
        )


def renumber(positions: Sequence[int]) -> list[int]:
    """1..N preservando a ordem de entrada. Usado após remover uma linha."""
    return list(range(1, len(positions) + 1))
