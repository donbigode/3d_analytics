from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from backend.core.models import ExpenseCategory


class SaleOut(BaseModel):
    id: str
    quote_id: str
    quote_status: str
    quote_total: Decimal
    cpv_calc: Decimal
    client_id: str | None
    is_stale: bool
    is_sold: bool
    confirmed_revenue: Decimal | None
    variable_costs: Decimal
    cpv_override: Decimal | None
    sold_at: date | None
    notes: str | None
    itens_label: str = ""


class SaleUpdate(BaseModel):
    is_sold: bool | None = None
    confirmed_revenue: Decimal | None = None
    variable_costs: Decimal | None = None
    cpv_override: Decimal | None = None
    sold_at: date | None = None
    notes: str | None = None


class SyncOut(BaseModel):
    created: int
    updated: int
    stale: int


class ExpenseCreate(BaseModel):
    category: ExpenseCategory
    description: str
    amount: Decimal
    incurred_at: date
    is_recurring: bool = False


class ExpenseUpdate(BaseModel):
    category: ExpenseCategory | None = None
    description: str | None = None
    amount: Decimal | None = None
    incurred_at: date | None = None
    is_recurring: bool | None = None


class ExpenseOut(BaseModel):
    id: str
    category: str
    description: str
    amount: Decimal
    incurred_at: date
    is_recurring: bool


class DreOut(BaseModel):
    receita_bruta: Decimal
    impostos: Decimal
    receita_liquida: Decimal
    cpv: Decimal
    custos_variaveis: Decimal
    lucro_bruto: Decimal
    despesas: dict[str, Decimal]
    custo_estoque: Decimal
    total_despesas: Decimal
    resultado_liquido: Decimal
    margem_liquida_pct: Decimal


class MonthlyDreOut(DreOut):
    month: str


class ProfitabilityRow(BaseModel):
    label: str
    receita: Decimal
    custo: Decimal
    margem: Decimal
    margem_pct: Decimal


class ProfitabilityOut(BaseModel):
    by_client: list[ProfitabilityRow]
    by_material: list[ProfitabilityRow]


class FactRow(BaseModel):
    sale_id: str
    quote_id: str
    quote_kind: str
    cliente: str
    status: str
    sold_at: date | None
    is_sold: bool
    receita_venda: Decimal
    custos_variaveis_venda: Decimal
    cpv_venda: Decimal
    item_id: str
    nome: str
    quantidade: int
    material_type: str
    cor_material: str | None
    cor_bobina: str | None
    filament_m: float | None
    filament_g: float | None
    gramas_total: Decimal
    custo_filamento_item: Decimal
    receita_item: Decimal
