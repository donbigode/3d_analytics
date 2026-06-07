from decimal import Decimal
from pydantic import BaseModel


class CardEstoque(BaseModel):
    total_grams: Decimal
    estimated_value: Decimal


class DashboardCards(BaseModel):
    receita: Decimal
    despesa: Decimal
    lucro: Decimal
    margem_pct: Decimal
    gasto_pessoal: Decimal
    orcamentos_por_estado: dict
    taxa_conversao_pct: Decimal
    estoque: CardEstoque


class DashboardCharts(BaseModel):
    receita_vs_despesa: list[dict]   # [{period, receita, despesa}]
    funil: dict                       # {orcado, aprovado, produzido, entregue}
    despesa_categorias: dict          # {filamento, energia, mao_obra, depreciacao}
    orcado_vs_real: list[dict]        # [{quote_id, orcado, real, variancia_pct}]


class DashboardLists(BaseModel):
    ultimos_orcamentos: list[dict]
    parados: list[dict]
    spools_baixos: list[dict]
    inbox: list[dict]


class DashboardOut(BaseModel):
    cards: DashboardCards
    charts: DashboardCharts
    lists: DashboardLists
