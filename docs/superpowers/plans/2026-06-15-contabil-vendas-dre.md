# Aba Contábil — Vendas materializadas + DRE — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar uma aba **Contábil** com uma entidade de venda materializada a partir dos orçamentos comerciais (só o que é confirmado vira receita), uma entidade de despesas avulsas, e um relatório DRE — passando a alimentar a parte financeira do dashboard a partir das vendas confirmadas.

**Architecture:** Duas tabelas novas (`sales`, `expenses`). Um helper de custo compartilhado (`core/accounting/cost.py`) extraído da lógica inline do `dashboard.py`, reutilizado por dashboard, sync e DRE. `sync_sales()` faz lazy upsert dos orçamentos comerciais *aprovado+* em `sales`, atualizando os campos-espelho e preservando os editáveis. DRE e dashboard agregam vendas confirmadas (`is_sold`) por `sold_at` e despesas por `incurred_at`.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend), pytest async, SvelteKit + TypeScript (frontend). Padrões existentes: rotas como `backend/api/routes/clients.py`, models como `backend/infra/db/models/client.py`, página como `frontend/src/routes/clients/+page.svelte`.

**Spec:** `docs/superpowers/specs/2026-06-15-contabil-vendas-dre-design.md`

---

## File Structure

**Backend — criar:**
- `backend/infra/db/models/sale.py` — model `Sale`
- `backend/infra/db/models/expense.py` — model `Expense`
- `backend/core/accounting/__init__.py`
- `backend/core/accounting/cost.py` — `QuoteCosts`, `apply_markup`, `compute_quote_costs`, `load_settings_row`
- `backend/core/accounting/sync.py` — `sync_sales`
- `backend/core/accounting/dre.py` — `compute_dre`
- `backend/api/schemas/accounting.py` — schemas Pydantic
- `backend/api/routes/accounting.py` — rotas REST
- `migrations/versions/0025_accounting.py` — tabelas `sales` + `expenses`

**Backend — modificar:**
- `backend/core/models.py` — enum `ExpenseCategory`
- `backend/infra/db/models/__init__.py` — exportar `Sale`, `Expense`
- `backend/app.py` + `backend/api/routes/__init__.py` — registrar router
- `backend/api/routes/dashboard.py` — usar helper compartilhado + ler financeiro das vendas
- `backend/tests/api/conftest.py` — limpar `sales`/`expenses` entre testes

**Backend — testes:**
- `backend/tests/core/test_accounting_cost.py`
- `backend/tests/core/test_accounting_sync.py`
- `backend/tests/core/test_accounting_dre.py`
- `backend/tests/api/test_accounting.py`
- `backend/tests/api/test_dashboard.py` (estender)

**Frontend:**
- `frontend/src/lib/types.ts` — tipos `Sale`, `Expense`, `Dre`
- `frontend/src/routes/accounting/+page.svelte` — página
- `frontend/src/routes/+layout.svelte` — item de menu

---

## Task 1: Enum `ExpenseCategory`

**Files:**
- Modify: `backend/core/models.py`

- [ ] **Step 1: Adicionar o enum**

No fim de `backend/core/models.py`, após `WatcherInboxStatus`:

```python
class ExpenseCategory(StrEnum):
    MAINTENANCE = "maintenance"
    PARTS = "parts"
    TOOLS = "tools"
    LABOR = "labor"
    OTHER = "other"
```

- [ ] **Step 2: Verificar import**

Run: `python -c "from backend.core.models import ExpenseCategory; print([c.value for c in ExpenseCategory])"`
Expected: `['maintenance', 'parts', 'tools', 'labor', 'other']`

- [ ] **Step 3: Commit**

```bash
git add backend/core/models.py
git commit -m "feat(contabil): enum ExpenseCategory"
```

---

## Task 2: Models `Sale` e `Expense`

**Files:**
- Create: `backend/infra/db/models/sale.py`
- Create: `backend/infra/db/models/expense.py`
- Modify: `backend/infra/db/models/__init__.py`

- [ ] **Step 1: Criar `sale.py`**

```python
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, false, func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class Sale(Base):
    """Linha contábil materializada a partir de um orçamento comercial.

    Campos-espelho (quote_status/quote_total/cpv_calc/client_id) são
    reescritos a cada sync. Campos editáveis (is_sold, confirmed_revenue,
    variable_costs, cpv_override, sold_at, notes) são preservados.
    """
    __tablename__ = "sales"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    # Espelho — reescrito no sync
    quote_status: Mapped[str] = mapped_column(String(20), nullable=False)
    quote_total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    cpv_calc: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    client_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL")
    )
    is_stale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Editável — preservado no sync
    is_sold: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    confirmed_revenue: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    variable_costs: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0"
    )
    cpv_override: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    sold_at: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: Criar `expense.py`**

```python
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class Expense(Base):
    """Despesa avulsa do DRE (manutenção, peças, ferramentas, mecânicos, outros)."""
    __tablename__ = "expenses"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    incurred_at: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 3: Exportar nos models**

Em `backend/infra/db/models/__init__.py`, adicionar os imports (em ordem alfabética junto aos demais) e ao `__all__`:

```python
from backend.infra.db.models.expense import Expense
from backend.infra.db.models.sale import Sale
```

E em `__all__` acrescentar `"Expense"` e `"Sale"`.

- [ ] **Step 4: Verificar import**

Run: `python -c "from backend.infra.db.models import Sale, Expense; print(Sale.__tablename__, Expense.__tablename__)"`
Expected: `sales expenses`

- [ ] **Step 5: Commit**

```bash
git add backend/infra/db/models/sale.py backend/infra/db/models/expense.py backend/infra/db/models/__init__.py
git commit -m "feat(contabil): models Sale e Expense"
```

---

## Task 2b: Migração Alembic

**Files:**
- Create: `migrations/versions/0025_accounting.py`
- Modify: `backend/tests/api/conftest.py`

- [ ] **Step 1: Criar a migração**

```python
"""tabelas sales + expenses (aba Contábil)

Revision ID: 0025_accounting
Revises: 0024_production_suggestions
Create Date: 2026-06-15 09:00:00.000000

sales: linha materializada por orçamento comercial aprovado+. Campos-espelho
(quote_status/quote_total/cpv_calc/client_id) + editáveis preservados no sync.
expenses: despesas avulsas do DRE.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "0025_accounting"
down_revision: Union[str, Sequence[str], None] = "0024_production_suggestions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sales",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("quote_id", UUID(as_uuid=True),
                  sa.ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("quote_status", sa.String(20), nullable=False),
        sa.Column("quote_total", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("cpv_calc", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("client_id", UUID(as_uuid=True),
                  sa.ForeignKey("clients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_stale", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_sold", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("confirmed_revenue", sa.Numeric(10, 2), nullable=True),
        sa.Column("variable_costs", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("cpv_override", sa.Numeric(10, 2), nullable=True),
        sa.Column("sold_at", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sales_sold_at", "sales", ["sold_at"])
    op.create_index("ix_sales_is_sold", "sales", ["is_sold"])

    op.create_table(
        "expenses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("incurred_at", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_expenses_incurred_at", "expenses", ["incurred_at"])


def downgrade() -> None:
    op.drop_table("expenses")
    op.drop_table("sales")
```

- [ ] **Step 2: Limpar tabelas novas nos testes**

Em `backend/tests/api/conftest.py`: importar `Sale, Expense` no bloco de imports de models, e adicionar à tupla de limpeza (antes de `Quote.__table__`, pois `sales` referencia `quotes`):

```python
                    Sale.__table__,
                    Expense.__table__,
```

(`Expense` não tem FK; pode ir em qualquer posição. `Sale` deve vir antes de `Quote` e `Client`.)

- [ ] **Step 3: Rodar a migração no banco de teste e confirmar**

Run: `alembic upgrade head`
Expected: termina sem erro; aplica `0025_accounting`.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0025_accounting.py backend/tests/api/conftest.py
git commit -m "feat(contabil): migração tabelas sales + expenses"
```

---

## Task 3: Helper de custo compartilhado

**Files:**
- Create: `backend/core/accounting/__init__.py` (vazio)
- Create: `backend/core/accounting/cost.py`
- Test: `backend/tests/core/test_accounting_cost.py`

Extrai o cálculo de custo hoje inline no `dashboard.py` para um único helper, reutilizado por dashboard, sync e DRE. `cost_orcado` usa filamento de catálogo (gcode × densidade × preço-ref); `cpv` usa filamento real consumido (snapshots de `MaterialConsumption`). Energia, depreciação e serviços são idênticos nos dois.

- [ ] **Step 1: Escrever o teste**

`backend/tests/core/test_accounting_cost.py`:

```python
from decimal import Decimal

import pytest

from backend.core.accounting.cost import apply_markup, compute_quote_costs
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialConsumption, MaterialVersion, Quote, QuoteItem, Settings, Spool, User,
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
        settings = Settings(id=1, energy_kwh_price=Decimal("1.00"),
                            printer_power_w=Decimal("100"),
                            printer_depreciation_per_hour=Decimal("0"))
        s.add_all([user, mv, settings]); await s.commit()
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
        # consumo real: 25 g a R$0,10/g = R$2,50
        cons = MaterialConsumption(quote_item_id=item.id, spool_id=spool.id,
                                   grams_used=Decimal("25"), unit_cost_snapshot=Decimal("0.10"))
        s.add(cons); await s.commit()

        costs = await compute_quote_costs(s, q, settings)
        # energia: 100W * 1h / 1000 * R$1 = R$0,10
        assert costs.energy == Decimal("0.10")
        assert costs.real_filament == Decimal("2.50")
        assert costs.cpv == costs.real_filament + costs.energy + costs.depreciation + costs.services
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest backend/tests/core/test_accounting_cost.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.core.accounting`.

- [ ] **Step 3: Implementar**

`backend/core/accounting/__init__.py`: arquivo vazio.

`backend/core/accounting/cost.py`:

```python
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
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest backend/tests/core/test_accounting_cost.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add backend/core/accounting/__init__.py backend/core/accounting/cost.py backend/tests/core/test_accounting_cost.py
git commit -m "feat(contabil): helper de custo compartilhado (QuoteCosts)"
```

---

## Task 4: Refatorar dashboard para usar o helper (sem mudar números)

**Files:**
- Modify: `backend/api/routes/dashboard.py`

Refactor puro: substituir o loop inline de custo pela chamada a `compute_quote_costs` + `apply_markup`. Os números do dashboard **não mudam** nesta task.

- [ ] **Step 1: Confirmar baseline verde**

Run: `pytest backend/tests/api/test_dashboard.py -v`
Expected: PASS (2 testes).

- [ ] **Step 2: Importar o helper**

Em `backend/api/routes/dashboard.py`, adicionar:

```python
from backend.core.accounting.cost import apply_markup, compute_quote_costs, load_settings_row
```

E remover as constantes locais `_DIAMETER_MM` e `_PI` (agora vivem no helper) — confirmar que não são mais usadas em outro ponto do arquivo (`grep _PI backend/api/routes/dashboard.py`).

- [ ] **Step 3: Substituir o cálculo por-quote**

Dentro do `for q in quotes:`, **substituir** todo o trecho que vai de `items = (...)` até a definição de `total = cost_orcado * (...)` e a função interna `_real_filament_for`, por:

```python
        costs = await compute_quote_costs(session, q, settings_row)
        item_energy = costs.energy
        item_dep = costs.depreciation
        services_cost = costs.services
        cost_orcado = costs.cost_orcado
        total = apply_markup(cost_orcado, q.markup_pct, q.min_charge)
        if total < q.min_charge:
            total = q.min_charge
```

Nos blocos seguintes que usavam `await _real_filament_for(items)`, trocar por `costs.real_filament`:
- em `is_commercial_produced`: `real_filament = costs.real_filament` e `real_cost = costs.cpv`.
- em `gasto_pessoal` (personal produzido): `real_filament_p = costs.real_filament` e `real_cost_p = costs.cpv`.

Ajustar `settings_row` para usar o helper de default: substituir o bloco
`settings_row = await session.get(Settings, 1)` + o `if settings_row is None:` por:

```python
    settings_row = load_settings_row(await session.get(Settings, 1))
```

- [ ] **Step 4: Rodar e ver passar (números preservados)**

Run: `pytest backend/tests/api/test_dashboard.py -v`
Expected: PASS (2 testes).

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/dashboard.py
git commit -m "refactor(dashboard): usar helper de custo compartilhado (sem mudança de número)"
```

---

## Task 5: `sync_sales` (lazy upsert)

**Files:**
- Create: `backend/core/accounting/sync.py`
- Test: `backend/tests/core/test_accounting_sync.py`

- [ ] **Step 1: Escrever o teste**

`backend/tests/core/test_accounting_sync.py`:

```python
from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.core.accounting.sync import sync_sales
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, Sale, User


async def _mk_quote(s, user, status, kind=QuoteKind.COMMERCIAL):
    q = Quote(kind=kind.value, user_id=user.id, status=status.value,
              markup_pct=Decimal("100"), min_charge=Decimal("0"))
    s.add(q); await s.commit()
    return q


@pytest.mark.asyncio
async def test_sync_creates_preserves_and_marks_stale():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="sync@t.com", password_hash="x")
        s.add(user); await s.commit()
        q_appr = await _mk_quote(s, user, QuoteStatus.APROVADO)
        q_pers = await _mk_quote(s, user, QuoteStatus.PRODUZIDO, kind=QuoteKind.PERSONAL)

    # 1º sync: cria linha só para o comercial; ignora o pessoal
    async with session_module.SessionFactory() as s:
        res = await sync_sales(s)
        assert res["created"] == 1
        sales = (await s.execute(select(Sale))).scalars().all()
        assert len(sales) == 1
        sale = sales[0]
        assert sale.quote_id == q_appr.id
        assert sale.is_sold is False
        # usuário confirma a venda na mão
        sale.is_sold = True
        sale.confirmed_revenue = Decimal("999")
        await s.commit()

    # 2º sync: preserva os editáveis, atualiza espelho
    async with session_module.SessionFactory() as s:
        res = await sync_sales(s)
        assert res["created"] == 0 and res["updated"] == 1
        sale = (await s.execute(select(Sale))).scalars().one()
        assert sale.is_sold is True
        assert sale.confirmed_revenue == Decimal("999")

    # orçamento sai de aprovado+ -> linha vira stale
    async with session_module.SessionFactory() as s:
        q = await s.get(Quote, q_appr.id)
        q.status = QuoteStatus.CANCELADO.value
        await s.commit()
        res = await sync_sales(s)
        assert res["stale"] == 1
        sale = (await s.execute(select(Sale))).scalars().one()
        assert sale.is_stale is True
        # editáveis seguem preservados
        assert sale.confirmed_revenue == Decimal("999")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest backend/tests/core/test_accounting_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.core.accounting.sync`.

- [ ] **Step 3: Implementar**

`backend/core/accounting/sync.py`:

```python
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.accounting.cost import apply_markup, compute_quote_costs, load_settings_row
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db.models import Quote, Sale, Settings

# Status considerados "candidatos a venda" (a partir de aprovado).
ACTIVE_STATUSES = (
    QuoteStatus.APROVADO.value,
    QuoteStatus.PRODUZIDO.value,
    QuoteStatus.ENTREGUE.value,
)


def _status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


async def sync_sales(session: AsyncSession) -> dict[str, int]:
    """Lazy upsert dos orçamentos comerciais aprovado+ na tabela `sales`.

    Sempre reescreve os campos-espelho; nunca toca nos editáveis. Linhas cujo
    orçamento saiu de aprovado+ viram `is_stale=True` (mantém histórico).
    """
    settings_row = load_settings_row(await session.get(Settings, 1))

    quotes = (
        await session.execute(
            select(Quote).where(
                Quote.kind == QuoteKind.COMMERCIAL.value,
                Quote.status.in_(ACTIVE_STATUSES),
            )
        )
    ).scalars().all()

    existing = {
        sale.quote_id: sale
        for sale in (await session.execute(select(Sale))).scalars().all()
    }

    created = updated = stale = 0
    active_ids: set = set()

    for q in quotes:
        active_ids.add(q.id)
        costs = await compute_quote_costs(session, q, settings_row)
        total = apply_markup(costs.cost_orcado, q.markup_pct, q.min_charge)

        sale = existing.get(q.id)
        if sale is None:
            sale = Sale(quote_id=q.id, is_sold=False, variable_costs=Decimal(0))
            session.add(sale)
            created += 1
        else:
            updated += 1

        sale.quote_status = _status_value(q.status)
        sale.quote_total = total
        sale.cpv_calc = costs.cpv
        sale.client_id = q.client_id
        sale.is_stale = False

    for quote_id, sale in existing.items():
        if quote_id not in active_ids and not sale.is_stale:
            sale.is_stale = True
            stale += 1

    await session.commit()
    return {"created": created, "updated": updated, "stale": stale}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest backend/tests/core/test_accounting_sync.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/accounting/sync.py backend/tests/core/test_accounting_sync.py
git commit -m "feat(contabil): sync_sales lazy upsert"
```

---

## Task 6: `compute_dre`

**Files:**
- Create: `backend/core/accounting/dre.py`
- Test: `backend/tests/core/test_accounting_dre.py`

- [ ] **Step 1: Escrever o teste**

`backend/tests/core/test_accounting_dre.py`:

```python
from datetime import date
from decimal import Decimal

import pytest

from backend.core.accounting.dre import compute_dre
from backend.core.models import ExpenseCategory, QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Expense, Quote, Sale, User


async def _mk_quote(s, user) -> Quote:
    """Sale.quote_id é NOT NULL com FK para quotes — cada Sale precisa de um Quote real."""
    q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
              status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"), min_charge=Decimal("0"))
    s.add(q); await s.commit()
    return q


@pytest.mark.asyncio
async def test_dre_aggregates_sold_sales_and_expenses():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="dre@t.com", password_hash="x")
        s.add(user); await s.commit()
        q1 = await _mk_quote(s, user)
        q2 = await _mk_quote(s, user)
        q3 = await _mk_quote(s, user)
        # venda confirmada no período: receita 1000, cpv 300, variável 50
        s.add(Sale(quote_id=q1.id, quote_status="entregue", quote_total=Decimal("1000"),
                   cpv_calc=Decimal("300"), is_sold=True, confirmed_revenue=Decimal("1000"),
                   variable_costs=Decimal("50"), sold_at=date(2026, 6, 10)))
        # venda NÃO confirmada — não entra
        s.add(Sale(quote_id=q2.id, quote_status="aprovado", quote_total=Decimal("500"),
                   cpv_calc=Decimal("200"), is_sold=False, sold_at=None))
        # venda confirmada fora do período — não entra
        s.add(Sale(quote_id=q3.id, quote_status="entregue", quote_total=Decimal("800"),
                   cpv_calc=Decimal("100"), is_sold=True, confirmed_revenue=Decimal("800"),
                   variable_costs=Decimal("0"), sold_at=date(2026, 1, 1)))
        s.add(Expense(category=ExpenseCategory.PARTS.value, description="bico",
                      amount=Decimal("40"), incurred_at=date(2026, 6, 12)))
        await s.commit()

    async with session_module.SessionFactory() as s:
        dre = await compute_dre(s, date(2026, 6, 1), date(2026, 6, 30))

    assert dre["receita_bruta"] == Decimal("1000.00")
    assert dre["cpv"] == Decimal("300.00")
    assert dre["custos_variaveis"] == Decimal("50.00")
    assert dre["lucro_bruto"] == Decimal("650.00")
    assert dre["despesas"]["parts"] == Decimal("40.00")
    assert dre["resultado_liquido"] == Decimal("610.00")
    # margem = 610 / 1000
    assert dre["margem_liquida_pct"] == Decimal("61.00")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest backend/tests/core/test_accounting_dre.py -v`
Expected: FAIL — `ModuleNotFoundError: backend.core.accounting.dre`.

- [ ] **Step 3: Implementar**

`backend/core/accounting/dre.py`:

```python
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import ExpenseCategory
from backend.infra.db.models import Expense, Sale


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


def _sale_cpv(sale: Sale) -> Decimal:
    return sale.cpv_override if sale.cpv_override is not None else sale.cpv_calc


async def compute_dre(session: AsyncSession, period_from: date, period_to: date) -> dict:
    """Agrega vendas confirmadas (por sold_at) e despesas (por incurred_at)."""
    sales = (
        await session.execute(
            select(Sale).where(
                Sale.is_sold.is_(True),
                Sale.sold_at.is_not(None),
                Sale.sold_at >= period_from,
                Sale.sold_at <= period_to,
            )
        )
    ).scalars().all()

    receita = sum((s.confirmed_revenue or Decimal(0) for s in sales), Decimal(0))
    cpv = sum((_sale_cpv(s) for s in sales), Decimal(0))
    variaveis = sum((s.variable_costs for s in sales), Decimal(0))
    lucro_bruto = receita - cpv - variaveis

    expenses = (
        await session.execute(
            select(Expense).where(
                Expense.incurred_at >= period_from,
                Expense.incurred_at <= period_to,
            )
        )
    ).scalars().all()

    despesas = {cat.value: Decimal(0) for cat in ExpenseCategory}
    for e in expenses:
        despesas[e.category] = despesas.get(e.category, Decimal(0)) + e.amount
    total_despesas = sum(despesas.values(), Decimal(0))

    resultado = lucro_bruto - total_despesas
    margem = (resultado / receita * Decimal(100)) if receita > 0 else Decimal(0)

    return {
        "receita_bruta": _q2(receita),
        "cpv": _q2(cpv),
        "custos_variaveis": _q2(variaveis),
        "lucro_bruto": _q2(lucro_bruto),
        "despesas": {k: _q2(v) for k, v in despesas.items()},
        "total_despesas": _q2(total_despesas),
        "resultado_liquido": _q2(resultado),
        "margem_liquida_pct": _q2(margem),
    }
```

- [ ] **Step 4: Rodar e ver passar**

Run: `pytest backend/tests/core/test_accounting_dre.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/accounting/dre.py backend/tests/core/test_accounting_dre.py
git commit -m "feat(contabil): compute_dre"
```

---

## Task 7: Schemas + rotas REST

**Files:**
- Create: `backend/api/schemas/accounting.py`
- Create: `backend/api/routes/accounting.py`
- Modify: `backend/app.py`, `backend/api/routes/__init__.py`
- Test: `backend/tests/api/test_accounting.py`

- [ ] **Step 1: Escrever o teste**

`backend/tests/api/test_accounting.py`:

```python
from decimal import Decimal

import pytest

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, User


async def _seed_commercial_quote() -> str:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(__import__("sqlalchemy").select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.APROVADO.value, markup_pct=Decimal("100"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        return str(q.id)


@pytest.mark.asyncio
async def test_sales_listed_after_sync_and_patch(auth_client):
    await _seed_commercial_quote()
    # GET dispara o sync e materializa a venda
    r = await auth_client.get("/accounting/sales")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    sale = rows[0]
    assert sale["is_sold"] is False

    # confirmar a venda
    r = await auth_client.patch(f"/accounting/sales/{sale['id']}", json={
        "is_sold": True, "confirmed_revenue": "1234.00", "sold_at": "2026-06-10",
    })
    assert r.status_code == 200, r.text
    assert r.json()["is_sold"] is True
    assert r.json()["confirmed_revenue"] == "1234.00"


@pytest.mark.asyncio
async def test_expenses_crud(auth_client):
    r = await auth_client.post("/accounting/expenses", json={
        "category": "parts", "description": "bico 0.4", "amount": "40.00",
        "incurred_at": "2026-06-12",
    })
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    r = await auth_client.get("/accounting/expenses")
    assert any(e["id"] == eid for e in r.json())
    r = await auth_client.patch(f"/accounting/expenses/{eid}", json={"amount": "55.00"})
    assert r.json()["amount"] == "55.00"
    r = await auth_client.delete(f"/accounting/expenses/{eid}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_dre_shape(auth_client):
    r = await auth_client.get("/accounting/dre?from=2026-06-01&to=2026-06-30")
    assert r.status_code == 200, r.text
    for key in ["receita_bruta", "cpv", "custos_variaveis", "lucro_bruto",
                "despesas", "resultado_liquido", "margem_liquida_pct"]:
        assert key in r.json()
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest backend/tests/api/test_accounting.py -v`
Expected: FAIL — 404 (rota não registrada).

- [ ] **Step 3: Schemas**

`backend/api/schemas/accounting.py`:

```python
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


class ExpenseUpdate(BaseModel):
    category: ExpenseCategory | None = None
    description: str | None = None
    amount: Decimal | None = None
    incurred_at: date | None = None


class ExpenseOut(BaseModel):
    id: str
    category: str
    description: str
    amount: Decimal
    incurred_at: date


class DreOut(BaseModel):
    receita_bruta: Decimal
    cpv: Decimal
    custos_variaveis: Decimal
    lucro_bruto: Decimal
    despesas: dict[str, Decimal]
    total_despesas: Decimal
    resultado_liquido: Decimal
    margem_liquida_pct: Decimal
```

- [ ] **Step 4: Rotas**

`backend/api/routes/accounting.py`:

```python
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.accounting import (
    DreOut, ExpenseCreate, ExpenseOut, ExpenseUpdate, SaleOut, SaleUpdate, SyncOut,
)
from backend.core.accounting.dre import compute_dre
from backend.core.accounting.sync import sync_sales
from backend.infra.db.models import Expense, Sale, User

router = APIRouter()


def _sale_out(s: Sale) -> SaleOut:
    return SaleOut(
        id=str(s.id), quote_id=str(s.quote_id), quote_status=s.quote_status,
        quote_total=s.quote_total, cpv_calc=s.cpv_calc,
        client_id=str(s.client_id) if s.client_id else None,
        is_stale=s.is_stale, is_sold=s.is_sold, confirmed_revenue=s.confirmed_revenue,
        variable_costs=s.variable_costs, cpv_override=s.cpv_override,
        sold_at=s.sold_at, notes=s.notes,
    )


def _expense_out(e: Expense) -> ExpenseOut:
    return ExpenseOut(id=str(e.id), category=e.category, description=e.description,
                      amount=e.amount, incurred_at=e.incurred_at)


@router.post("/sync", response_model=SyncOut)
async def run_sync(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    return SyncOut(**await sync_sales(session))


@router.get("/sales", response_model=list[SaleOut])
async def list_sales(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    is_sold: bool | None = Query(None),
    is_stale: bool | None = Query(None),
):
    await sync_sales(session)  # lazy: materializa ao abrir a aba
    stmt = select(Sale).order_by(Sale.created_at.desc())
    if is_sold is not None:
        stmt = stmt.where(Sale.is_sold.is_(is_sold))
    if is_stale is not None:
        stmt = stmt.where(Sale.is_stale.is_(is_stale))
    rows = (await session.execute(stmt)).scalars().all()
    return [_sale_out(s) for s in rows]


@router.patch("/sales/{sale_id}", response_model=SaleOut)
async def update_sale(
    sale_id: UUID, payload: SaleUpdate,
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
):
    sale = await session.get(Sale, sale_id)
    if not sale:
        raise HTTPException(404)
    data = payload.model_dump(exclude_unset=True)
    # Conveniência: ao confirmar a venda sem informar valor/data, usa defaults.
    if data.get("is_sold") and sale.confirmed_revenue is None and "confirmed_revenue" not in data:
        data["confirmed_revenue"] = sale.quote_total
    if data.get("is_sold") and sale.sold_at is None and "sold_at" not in data:
        data["sold_at"] = datetime.now(timezone.utc).date()
    for k, v in data.items():
        setattr(sale, k, v)
    await session.commit(); await session.refresh(sale)
    return _sale_out(sale)


@router.get("/expenses", response_model=list[ExpenseOut])
async def list_expenses(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    rows = (
        await session.execute(select(Expense).order_by(Expense.incurred_at.desc()))
    ).scalars().all()
    return [_expense_out(e) for e in rows]


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
async def create_expense(
    payload: ExpenseCreate,
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
):
    e = Expense(category=payload.category.value, description=payload.description,
                amount=payload.amount, incurred_at=payload.incurred_at)
    session.add(e); await session.commit(); await session.refresh(e)
    return _expense_out(e)


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
async def update_expense(
    expense_id: UUID, payload: ExpenseUpdate,
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
):
    e = await session.get(Expense, expense_id)
    if not e:
        raise HTTPException(404)
    data = payload.model_dump(exclude_unset=True)
    if "category" in data and data["category"] is not None:
        data["category"] = data["category"].value
    for k, v in data.items():
        setattr(e, k, v)
    await session.commit(); await session.refresh(e)
    return _expense_out(e)


@router.delete("/expenses/{expense_id}", status_code=204)
async def delete_expense(
    expense_id: UUID,
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
):
    e = await session.get(Expense, expense_id)
    if not e:
        raise HTTPException(404)
    await session.delete(e); await session.commit()


@router.get("/dre", response_model=DreOut)
async def dre(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    from_: date = Query(..., alias="from"),
    to: date = Query(...),
):
    return DreOut(**await compute_dre(session, from_, to))
```

- [ ] **Step 5: Registrar o router**

Em `backend/api/routes/__init__.py` o arquivo está vazio — o `app.py` importa do pacote. Em `backend/app.py`:

No bloco `from backend.api.routes import (...)`, acrescentar `accounting,` à lista. Depois dos outros `include_router`, adicionar:

```python
app.include_router(accounting.router, prefix="/accounting", tags=["accounting"])
```

- [ ] **Step 6: Rodar e ver passar**

Run: `pytest backend/tests/api/test_accounting.py -v`
Expected: PASS (3 testes).

- [ ] **Step 7: Commit**

```bash
git add backend/api/schemas/accounting.py backend/api/routes/accounting.py backend/app.py backend/tests/api/test_accounting.py
git commit -m "feat(contabil): rotas REST de vendas, despesas e DRE"
```

---

## Task 8: Dashboard lê o financeiro das vendas confirmadas

**Files:**
- Modify: `backend/api/routes/dashboard.py`
- Test: `backend/tests/api/test_dashboard.py`

A receita/despesa/lucro/margem e o gráfico `receita_vs_despesa` passam a vir das vendas confirmadas + despesas. O funil, gasto_pessoal, estoque, listas, `despesa_categorias` e `orcado_vs_real` **continuam** vindo do loop de orçamentos.

- [ ] **Step 1: Escrever o teste**

Acrescentar a `backend/tests/api/test_dashboard.py`:

```python
@pytest.mark.asyncio
async def test_dashboard_receita_from_confirmed_sale(auth_client):
    """Receita do dashboard vem da venda confirmada, não do status do orçamento."""
    from datetime import date
    from decimal import Decimal
    from backend.core.models import QuoteKind, QuoteStatus
    from backend.infra.db import session as session_module
    from backend.infra.db.models import Quote, Sale, User
    import sqlalchemy as sa

    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        s.add(Sale(quote_id=q.id, quote_status="entregue", quote_total=Decimal("500"),
                   cpv_calc=Decimal("100"), is_sold=True, confirmed_revenue=Decimal("777"),
                   variable_costs=Decimal("0"), sold_at=date.today()))
        await s.commit()

    r = await auth_client.get("/dashboard")
    assert r.status_code == 200, r.text
    assert r.json()["cards"]["receita"] == "777.00"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `pytest backend/tests/api/test_dashboard.py::test_dashboard_receita_from_confirmed_sale -v`
Expected: FAIL — receita vem do status (valor != "777.00").

- [ ] **Step 3: Implementar a troca de fonte**

Em `backend/api/routes/dashboard.py`:

3a. Importar no topo:

```python
from backend.core.accounting.sync import sync_sales
from backend.core.accounting.dre import _sale_cpv
from backend.infra.db.models import Expense, Sale
```

3b. Logo após calcular `period_from`/`period_to`, rodar o sync e definir as bordas em `date`:

```python
    await sync_sales(session)
    pf_date = period_from.date()
    pt_date = period_to.date()
```

3c. **Remover** do loop `for q in quotes:` as linhas que acumulavam receita/despesa por status e os writes em `rev_exp_buckets`. Especificamente, apagar:
- o bloco `if is_commercial_revenue:` inteiro (incluindo o cálculo de `is_commercial_revenue` e o bucket de receita);
- dentro de `if is_commercial_produced:`, apagar `despesa += real_cost` e o bloco do bucket G1 (`ts = q.produced_at ...` + `slot[...]["despesa"] += real_cost`). **Manter** as linhas `cat_totals[...] += ...` (categoria) e o bloco `orcado_vs_real_rows.append(...)`.

Manter `receita = Decimal(0)` e `despesa = Decimal(0)` declarados antes do loop (serão sobrescritos abaixo).

3d. **Depois** do loop (logo antes de `lucro = receita - despesa`), inserir o cálculo a partir das vendas/despesas:

```python
    confirmed = (
        await session.execute(
            select(Sale).where(
                Sale.is_sold.is_(True),
                Sale.sold_at.is_not(None),
                Sale.sold_at >= pf_date,
                Sale.sold_at <= pt_date,
            )
        )
    ).scalars().all()
    receita = sum((s.confirmed_revenue or Decimal(0) for s in confirmed), Decimal(0))
    despesa_vendas = sum((_sale_cpv(s) + s.variable_costs for s in confirmed), Decimal(0))

    op_expenses = (
        await session.execute(
            select(Expense).where(
                Expense.incurred_at >= pf_date,
                Expense.incurred_at <= pt_date,
            )
        )
    ).scalars().all()
    despesa_ops = sum((e.amount for e in op_expenses), Decimal(0))
    despesa = despesa_vendas + despesa_ops

    # Gráfico receita_vs_despesa: receita+custo de venda por sold_at; despesa op. por incurred_at
    rev_exp_buckets = {}
    for s in confirmed:
        bk = _bucket_key(datetime(s.sold_at.year, s.sold_at.month, s.sold_at.day), bucket_mode)
        slot = rev_exp_buckets.setdefault(bk, {"receita": Decimal(0), "despesa": Decimal(0)})
        slot["receita"] += s.confirmed_revenue or Decimal(0)
        slot["despesa"] += _sale_cpv(s) + s.variable_costs
    for e in op_expenses:
        bk = _bucket_key(datetime(e.incurred_at.year, e.incurred_at.month, e.incurred_at.day), bucket_mode)
        slot = rev_exp_buckets.setdefault(bk, {"receita": Decimal(0), "despesa": Decimal(0)})
        slot["despesa"] += e.amount
```

(Como `rev_exp_buckets` agora é construído aqui, remover sua inicialização anterior `rev_exp_buckets: dict[...] = {}` de antes do loop para não zerar duas vezes — ou deixá-la; a reatribuição acima prevalece. Preferir remover a antiga para clareza.)

- [ ] **Step 4: Rodar e ver passar (todo o dashboard)**

Run: `pytest backend/tests/api/test_dashboard.py -v`
Expected: PASS (3 testes — os 2 originais + o novo).

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/dashboard.py backend/tests/api/test_dashboard.py
git commit -m "feat(dashboard): receita/despesa a partir das vendas confirmadas + despesas"
```

---

## Task 9: Suíte backend completa verde

**Files:** nenhuma alteração — gate de verificação.

- [ ] **Step 1: Rodar a suíte inteira**

Run: `pytest backend/tests -q`
Expected: tudo PASS. Se algum teste pré-existente quebrar por causa da mudança de fonte de receita no dashboard, investigar com a skill `systematic-debugging` antes de seguir.

- [ ] **Step 2: Commit (se houve ajuste)**

```bash
git add -A && git commit -m "test(contabil): suíte backend verde"
```

---

## Task 10: Tipos do frontend

**Files:**
- Modify: `frontend/src/lib/types.ts`

- [ ] **Step 1: Adicionar tipos**

Acrescentar a `frontend/src/lib/types.ts`:

```typescript
export type Sale = {
  id: string;
  quote_id: string;
  quote_status: string;
  quote_total: string;
  cpv_calc: string;
  client_id: string | null;
  is_stale: boolean;
  is_sold: boolean;
  confirmed_revenue: string | null;
  variable_costs: string;
  cpv_override: string | null;
  sold_at: string | null;
  notes: string | null;
};

export type ExpenseCategory = "maintenance" | "parts" | "tools" | "labor" | "other";

export type Expense = {
  id: string;
  category: ExpenseCategory;
  description: string;
  amount: string;
  incurred_at: string;
};

export type Dre = {
  receita_bruta: string;
  cpv: string;
  custos_variaveis: string;
  lucro_bruto: string;
  despesas: Record<string, string>;
  total_despesas: string;
  resultado_liquido: string;
  margem_liquida_pct: string;
};
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npm run check`
Expected: sem erros novos.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/types.ts
git commit -m "feat(contabil): tipos Sale/Expense/Dre no frontend"
```

---

## Task 11: Página `/accounting` (aba Contábil)

**Files:**
- Create: `frontend/src/routes/accounting/+page.svelte`
- Modify: `frontend/src/routes/+layout.svelte`

Seguir o padrão de `frontend/src/routes/clients/+page.svelte` (imports `api`, `errorMessage`, `handleApiError`, `requireAuth`, componentes `Table`/`Form`) e a skill `frontend-design` para o capricho visual. Três sub-abas via uma variável `tab` (`"vendas" | "despesas" | "dre"`).

- [ ] **Step 1: Criar a página**

`frontend/src/routes/accounting/+page.svelte` — estrutura mínima funcional (refinar o visual seguindo `frontend-design`):

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import { api, errorMessage } from "$lib/api";
  import { handleApiError, requireAuth } from "$lib/guard";
  import Table from "$lib/components/Table.svelte";
  import type { Sale, Expense, Dre, ExpenseCategory } from "$lib/types";

  let tab: "vendas" | "despesas" | "dre" = "vendas";

  // vendas
  let sales: Sale[] = [];
  let salesError = "";
  let showStale = false;

  // despesas
  let expenses: Expense[] = [];
  let expError = "";
  let exCategory: ExpenseCategory = "maintenance";
  let exDescription = "";
  let exAmount = "";
  let exDate = new Date().toISOString().slice(0, 10);

  // dre
  let dre: Dre | null = null;
  let from = new Date().toISOString().slice(0, 8) + "01";
  let to = new Date().toISOString().slice(0, 10);

  const CATS: { value: ExpenseCategory; label: string }[] = [
    { value: "maintenance", label: "Manutenção" },
    { value: "parts", label: "Peças" },
    { value: "tools", label: "Ferramentas" },
    { value: "labor", label: "Mecânicos" },
    { value: "other", label: "Outros" },
  ];
  const catLabel = (c: string) => CATS.find((x) => x.value === c)?.label ?? c;

  async function loadSales() {
    salesError = "";
    try {
      sales = await api<Sale[]>(`/accounting/sales${showStale ? "" : "?is_stale=false"}`);
    } catch (err) { handleApiError(err); salesError = errorMessage(err, "Falha ao carregar vendas."); }
  }

  async function patchSale(s: Sale, body: Partial<Sale>) {
    try {
      await api<Sale>(`/accounting/sales/${s.id}`, {
        method: "PATCH", headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      await loadSales();
    } catch (err) { handleApiError(err); salesError = errorMessage(err, "Falha ao salvar venda."); }
  }

  async function loadExpenses() {
    expError = "";
    try { expenses = await api<Expense[]>("/accounting/expenses"); }
    catch (err) { handleApiError(err); expError = errorMessage(err, "Falha ao carregar despesas."); }
  }

  async function createExpense() {
    expError = "";
    try {
      await api<Expense>("/accounting/expenses", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ category: exCategory, description: exDescription,
                               amount: exAmount, incurred_at: exDate }),
      });
      exDescription = ""; exAmount = "";
      await loadExpenses();
    } catch (err) { handleApiError(err); expError = errorMessage(err, "Falha ao criar despesa."); }
  }

  async function removeExpense(id: string) {
    if (!confirm("Remover esta despesa?")) return;
    try { await api(`/accounting/expenses/${id}`, { method: "DELETE" }); await loadExpenses(); }
    catch (err) { handleApiError(err); expError = errorMessage(err, "Falha ao remover."); }
  }

  async function loadDre() {
    try { dre = await api<Dre>(`/accounting/dre?from=${from}&to=${to}`); }
    catch (err) { handleApiError(err); }
  }

  onMount(() => {
    if (requireAuth()) return;
    loadSales(); loadExpenses(); loadDre();
  });
</script>

<header class="page-head">
  <span class="page-eyebrow">Financeiro</span>
  <h1 class="page-title">Contábil<em>.</em></h1>
  <p class="page-lede">Vendas confirmadas viram receita; despesas avulsas entram no DRE.</p>
</header>

<nav class="tabs">
  <button class:active={tab === "vendas"} on:click={() => (tab = "vendas")}>Vendas</button>
  <button class:active={tab === "despesas"} on:click={() => (tab = "despesas")}>Despesas</button>
  <button class:active={tab === "dre"} on:click={() => { tab = "dre"; loadDre(); }}>DRE</button>
</nav>

{#if tab === "vendas"}
  <section class="panel">
    <div class="panel-head">
      <h2 class="section-title">Vendas <span class="count">· {sales.length}</span></h2>
      <label class="inline"><input type="checkbox" bind:checked={showStale} on:change={loadSales} /> mostrar arquivadas</label>
      <button class="tiny ghost" on:click={loadSales}>Atualizar</button>
    </div>
    {#if salesError}<div class="alert">{salesError}</div>{/if}
    <Table
      columns={[
        { key: "quote_status", label: "Status" },
        { key: "quote_total", label: "Total", mono: true },
        { key: "cpv_calc", label: "CPV", mono: true },
      ]}
      rows={sales}
      empty="Nenhuma venda candidata"
    >
      <svelte:fragment slot="actions" let:row>
        <label class="inline">
          <input type="checkbox" checked={(row as Sale).is_sold}
                 on:change={(e) => patchSale(row as Sale, { is_sold: e.currentTarget.checked })} />
          Vendido
        </label>
        <input class="mini" type="number" step="0.01"
               value={(row as Sale).confirmed_revenue ?? (row as Sale).quote_total}
               on:change={(e) => patchSale(row as Sale, { confirmed_revenue: e.currentTarget.value })} />
      </svelte:fragment>
    </Table>
  </section>
{:else if tab === "despesas"}
  <section class="panel">
    <form class="form-grid" on:submit|preventDefault={createExpense}>
      <label class="field">Categoria
        <select bind:value={exCategory}>
          {#each CATS as c}<option value={c.value}>{c.label}</option>{/each}
        </select>
      </label>
      <label class="field">Descrição<input bind:value={exDescription} required /></label>
      <label class="field">Valor<input type="number" step="0.01" bind:value={exAmount} required /></label>
      <label class="field">Data<input type="date" bind:value={exDate} required /></label>
      <div class="actions"><button type="submit">Adicionar</button></div>
    </form>
    {#if expError}<div class="alert">{expError}</div>{/if}
    <Table
      columns={[
        { key: "category", label: "Categoria", format: catLabel },
        { key: "description", label: "Descrição" },
        { key: "amount", label: "Valor", mono: true },
        { key: "incurred_at", label: "Data", mono: true },
      ]}
      rows={expenses}
      empty="Nenhuma despesa lançada"
    >
      <svelte:fragment slot="actions" let:row>
        <button class="tiny danger" on:click={() => removeExpense((row as Expense).id)}>Excluir</button>
      </svelte:fragment>
    </Table>
  </section>
{:else}
  <section class="panel">
    <div class="panel-head">
      <label class="inline">De <input type="date" bind:value={from} /></label>
      <label class="inline">Até <input type="date" bind:value={to} /></label>
      <button class="tiny ghost" on:click={loadDre}>Gerar</button>
    </div>
    {#if dre}
      <dl class="dre">
        <div><dt>Receita bruta</dt><dd>{dre.receita_bruta}</dd></div>
        <div><dt>(−) CPV</dt><dd>{dre.cpv}</dd></div>
        <div><dt>(−) Custos variáveis</dt><dd>{dre.custos_variaveis}</dd></div>
        <div class="sub"><dt>= Lucro bruto</dt><dd>{dre.lucro_bruto}</dd></div>
        {#each Object.entries(dre.despesas) as [cat, val]}
          <div><dt>(−) {catLabel(cat)}</dt><dd>{val}</dd></div>
        {/each}
        <div class="total"><dt>= Resultado líquido</dt><dd>{dre.resultado_liquido}</dd></div>
        <div><dt>Margem líquida</dt><dd>{dre.margem_liquida_pct}%</dd></div>
      </dl>
    {/if}
  </section>
{/if}

<style>
  .tabs { display: flex; gap: 0.5rem; margin: 1.5rem 0; }
  .tabs button { padding: 0.5rem 1rem; }
  .tabs button.active { font-weight: 700; }
  .inline { display: inline-flex; align-items: center; gap: 0.3rem; }
  .mini { width: 6rem; }
  .dre dt { display: inline-block; min-width: 16rem; }
  .dre .total { font-weight: 700; }
</style>
```

Nota: o componente `Table` pode não suportar a prop `format` na coluna. Verificar `frontend/src/lib/components/Table.svelte`; se não suportar, formatar a categoria fora da tabela (slot) ou adicionar suporte mínimo a `format` na coluna seguindo o padrão do componente.

- [ ] **Step 2: Adicionar ao menu**

Em `frontend/src/routes/+layout.svelte`, no grupo `"Operação"` (ou criar item junto ao Dashboard), acrescentar ao array `items`:

```javascript
        { href: "/accounting", label: "Contábil", match: (p) => p.startsWith("/accounting") },
```

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npm run check`
Expected: sem erros.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/accounting/+page.svelte frontend/src/routes/+layout.svelte
git commit -m "feat(contabil): aba Contábil (Vendas/Despesas/DRE)"
```

---

## Task 12: Verificação final

**Files:** nenhuma — gate.

- [ ] **Step 1: Backend verde**

Run: `pytest backend/tests -q`
Expected: tudo PASS.

- [ ] **Step 2: Frontend check**

Run: `cd frontend && npm run check`
Expected: sem erros.

- [ ] **Step 3: Smoke manual (opcional, skill `verify`/`run`)**

Subir o app, abrir **Contábil**, confirmar uma venda, lançar uma despesa, gerar o DRE, e conferir que o card de receita do Dashboard reflete a venda confirmada.

- [ ] **Step 4: Finalizar a branch**

Usar a skill `superpowers:finishing-a-development-branch` para decidir merge/PR.

---

## Notas de implementação

- **Divergência intencional:** o card `despesa` do dashboard (DRE-aligned: CPV+variáveis das vendas confirmadas + despesas) **não** bate com o gráfico `despesa_categorias` (custo de produção dos orçamentos produzidos). São visões diferentes, ambas mantidas de propósito (ver spec §5).
- **`_sale_cpv` reutilizado:** o dashboard importa `_sale_cpv` de `core/accounting/dre.py` para aplicar a mesma regra `coalesce(cpv_override, cpv_calc)`. Se preferir não importar um símbolo "privado", promover para `sale_cpv` (público) em `dre.py` e atualizar os dois call sites.
- **Personal fora:** orçamentos pessoais nunca viram `Sale` (consomem estoque, não são receita — `personal_quotes_consume_stock`).
