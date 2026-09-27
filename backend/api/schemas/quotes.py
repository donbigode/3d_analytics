from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field

from backend.core.models import QuoteKind, QuoteStatus


class QuoteCreate(BaseModel):
    kind: QuoteKind
    client_id: str | None = None
    notes: str | None = None
    markup_pct: Decimal = Decimal("0")
    min_charge: Decimal = Decimal("0")


class QuoteUpdate(BaseModel):
    client_id: str | None = None
    notes: str | None = None
    markup_pct: Decimal | None = None
    min_charge: Decimal | None = None
    retail_mode: bool | None = None


class QuotePhotoOut(BaseModel):
    id: str
    quote_item_id: str | None
    url: str
    width: int
    height: int
    sort_order: int


class ConsumptionOut(BaseModel):
    """Uma baixa de material: qual bobina, quantas gramas, a que custo e quando.

    Um ciclo de produção por linha — reimpressão depois de falha aparece
    como entrada adicional, com data própria.
    """
    spool_id: str
    spool_label: str
    material_type: str
    color: str | None
    manufacturer: str | None
    grams_used: Decimal
    unit_cost_snapshot: Decimal
    # grams_used * unit_cost_snapshot, sem arredondar por linha — o contábil
    # (backend/core/accounting/cost.py) soma consumos sem arredondar e só
    # arredonda o agregado. Quem exibe é responsável por formatar em centavos.
    custo_total: Decimal
    consumed_at: datetime
    # Qual linha de filamento originou este consumo. None = consumo anterior à
    # 0034, ou baixa feita sem identificar a cor.
    filament_id: str | None = None


class QuoteItemFilamentOut(BaseModel):
    """Um filamento orçado do item — uma cor.

    Lado de leitura. O lado de escrita (`QuoteItemFilamentIn`) mora com a rota
    que troca a lista inteira.
    """
    id: str
    material_id: str
    material_name: str
    material_color: str | None = None
    # Gramas POR PEÇA. None = "derive do gcode_meta", que é o caso de todo item
    # anterior à migração 0034 — a tela mostra o derivado em cinza.
    grams_unit: Decimal | None = None
    position: int


class QuoteItemFilamentIn(BaseModel):
    material_id: str
    # `gt=0`: `None` já significa "não informado", então um `0` que chega aqui veio
    # de erro — tela que limpa o campo mandando 0 em vez de null. Sem a guarda,
    # aquela linha custaria zero em silêncio, sem cair no fallback do gcode.
    # (Achado na review da Task 3: a função espelhada, `effective_grams_per_unit`,
    # exige `filament_g > 0`, e este campo não exigia nada.)
    grams_unit: Decimal | None = Field(default=None, gt=0)
    # Sem `position`: a ORDEM DA LISTA é a posição. Aceitar posição do cliente
    # abriria espaço para um conjunto inconsistente que o servidor teria de
    # rejeitar — mais um caminho de erro por nada.


class QuoteItemOut(BaseModel):
    id: str
    name: str
    filename: str | None = None
    gcode_meta: dict
    quantity: int
    subtotal: Decimal
    # MaterialVersion UUID actually bound to this item — surfaced so the UI
    # can preselect it in the inline material dropdown. ``None`` when the
    # gcode was uploaded but no material was resolved.
    material_id: str | None = None
    is_multi_color: bool = False
    material_pending: bool = False
    pending_material_code: str | None = None
    model_source_url: str | None = None
    model_source_author: str | None = None
    model_source_license: str | None = None
    photos: list[QuotePhotoOut] = []
    # Filamentos orçados — um por cor. Ordenados por position.
    filaments: list[QuoteItemFilamentOut] = []
    # Filamento efetivamente baixado das bobinas — pode ter mais de uma linha
    # quando houve reimpressão (falha + nova tentativa consome duas vezes).
    consumptions: list[ConsumptionOut] = []


class QuoteItemUpdate(BaseModel):
    name: str | None = None
    quantity: int | None = None
    # UUID of the chosen MaterialVersion (preferred). Used when the user
    # resolves a pending item or switches to a different product line.
    material_id: str | None = None
    # Legacy: polymer type string. Still accepted — auto-resolves when there's
    # exactly one current material of that type; rejects with 400 otherwise.
    material_code: str | None = None
    # Manual overrides for gcode metadata — used when the slicer dialect
    # wasn't recognised on upload or the user wants to correct the parse.
    time_s: float | None = None
    filament_m: float | None = None
    filament_g: float | None = None
    is_multi_color: bool | None = None
    model_source_url: str | None = None
    model_source_author: str | None = None
    model_source_license: str | None = None
    # Substituição da lista inteira. None = não mexer (um PATCH que só muda o
    # nome não deve apagar as linhas). As invariantes são do CONJUNTO, e por
    # isso não há endpoint por linha: validar um conjunto em três endpoints
    # seria três lugares para a mesma regra divergir.
    filaments: list[QuoteItemFilamentIn] | None = None


class QuoteServiceOut(BaseModel):
    id: str
    service_id: str
    quantity: Decimal
    rate: Decimal
    subtotal: Decimal


class QuoteOut(BaseModel):
    id: str
    seq: int
    kind: QuoteKind
    client_id: str | None
    status: QuoteStatus
    markup_pct: Decimal
    min_charge: Decimal
    retail_mode: bool = False
    notes: str | None
    items: list[QuoteItemOut]
    services: list[QuoteServiceOut]
    cost: Decimal
    total: Decimal
    pending_items: int = 0
    created_at: datetime
    finalized_at: datetime | None
    approved_at: datetime | None
    produced_at: datetime | None
    delivered_at: datetime | None
    photos: list[QuotePhotoOut] = []
    person_ids: list[str] = []


class QuotePeopleUpdate(BaseModel):
    person_ids: list[str]


class ConsumptionAssignment(BaseModel):
    quote_item_id: str
    spool_id: str
    # Qual linha de filamento esta baixa representa. Obrigatório quando o item
    # tem mais de uma linha: sem isso o fallback calcularia as gramas do item
    # INTEIRO para cada linha, debitando N× o item.
    quote_item_filament_id: str | None = None
    # Overrides informados na hora de produzir (quando o gcode não trouxe a
    # metragem). `grams` = total a debitar para a linha; tem precedência.
    # `filament_m` = metragem por unidade; calcula as gramas e é persistida
    # no item (para custo/analytics refletirem).
    grams: Decimal | None = None
    filament_m: float | None = None


class ProduceRequest(BaseModel):
    consumption: list[ConsumptionAssignment]


class CompleteRequest(BaseModel):
    attempts: int = 1


class FailRequest(BaseModel):
    failure_description: str
    attempts: int = 1


class ServiceLineCreate(BaseModel):
    service_id: str
    quantity: Decimal
    rate: Decimal | None = None  # if None, uses service.default_rate
