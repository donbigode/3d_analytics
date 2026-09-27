from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from backend.core.models import SpoolStatus


class SpoolCreate(BaseModel):
    material_type: str
    color: str | None = None
    manufacturer: str | None = None
    purchased_from: str | None = None  # onde foi comprado (loja/marketplace)
    purchase_url: str | None = None    # link da compra
    purchased_at: datetime
    purchased_price: Decimal
    initial_grams: Decimal
    remaining_grams: Decimal
    status: SpoolStatus = SpoolStatus.OPEN
    notes: str | None = None


class SpoolUpdate(BaseModel):
    material_type: str | None = None
    color: str | None = None
    manufacturer: str | None = None
    purchased_from: str | None = None
    purchase_url: str | None = None
    purchased_at: datetime | None = None
    purchased_price: Decimal | None = None
    initial_grams: Decimal | None = None
    remaining_grams: Decimal | None = None
    status: SpoolStatus | None = None
    notes: str | None = None


class SpoolOut(BaseModel):
    id: str
    # Qual produto (MaterialVersion) está neste rolo. IDENTIDADE, NÃO PREÇO: a
    # tela de produzir usa para pré-selecionar a bobina da cor certa (casamento
    # exato; `material_type` é frouxo e adivinha errado), e o custo da baixa
    # continua saindo do `purchased_price / initial_grams` da própria bobina,
    # nunca do `price_per_kg_ref` do material.
    #
    # `None` é normal: o backfill da 0035 deixou o vínculo nulo em toda bobina
    # que não casou com certeza.
    material_version_id: str | None = None
    material_type: str
    color: str | None
    manufacturer: str | None
    purchased_from: str | None
    purchase_url: str | None
    purchased_at: datetime
    purchased_price: Decimal
    initial_grams: Decimal
    remaining_grams: Decimal
    status: SpoolStatus
    notes: str | None
