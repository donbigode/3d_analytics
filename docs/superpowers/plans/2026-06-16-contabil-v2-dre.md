# Contábil v2 — DRE/modelo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evoluir o DRE: pessoais viram venda, custo de estoque (consumo não vendido) entra como despesa, despesas recorrentes e categoria Máquinas, imposto sobre receita, e vendas stale saem do DRE — com o dashboard alinhado.

**Architecture:** Adiciona 3 colunas (migração), amplia `sync_sales` (inclui pessoais + `quote_kind`), reescreve `compute_dre` (impostos→receita líquida, custo de estoque, recorrentes, stale, equipment) e alinha o dashboard à mesma fonte. Tudo on-demand, sem mudar o consumo real registrado.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic, pytest via `docker compose run --rm api pytest …`, SvelteKit (`cd frontend && npm run check`).

**Spec:** `docs/superpowers/specs/2026-06-16-contabil-v2-design.md`

---

## File Structure

- `migrations/versions/0026_contabil_v2.py` — colunas `sales.quote_kind`, `expenses.is_recurring`, `settings.revenue_tax_pct`.
- `backend/infra/db/models/sale.py` / `expense.py` / `settings.py` — campos novos.
- `backend/core/models.py` — `ExpenseCategory.EQUIPMENT`.
- `backend/core/accounting/sync.py` — inclui pessoais + grava `quote_kind`.
- `backend/core/accounting/dre.py` — `compute_dre` v2 (+ helper de custo de estoque + expansão de recorrentes).
- `backend/api/schemas/accounting.py` / `routes/accounting.py` — `is_recurring` no CRUD; `DreOut` v2.
- `backend/api/schemas/settings.py` / `routes/settings.py` / model — `revenue_tax_pct`.
- `backend/api/routes/dashboard.py` — stale + custo de estoque + imposto.
- `frontend`: `lib/types.ts`, `routes/accounting/+page.svelte`, `routes/settings/+page.svelte`.

---

## Task 1: Migração — 3 colunas novas

**Files:**
- Create: `migrations/versions/0026_contabil_v2.py`
- Modify: `backend/infra/db/models/sale.py`, `expense.py`, `settings.py`

- [ ] **Step 1: Migração**

```python
"""contabil v2: sales.quote_kind, expenses.is_recurring, settings.revenue_tax_pct

Revision ID: 0026_contabil_v2
Revises: 0025_accounting
Create Date: 2026-06-16 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0026_contabil_v2"
down_revision: Union[str, Sequence[str], None] = "0025_accounting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales", sa.Column("quote_kind", sa.String(20), nullable=False,
                                     server_default="commercial"))
    op.add_column("expenses", sa.Column("is_recurring", sa.Boolean, nullable=False,
                                        server_default=sa.false()))
    op.add_column("settings", sa.Column("revenue_tax_pct", sa.Numeric(5, 2), nullable=False,
                                        server_default="0"))


def downgrade() -> None:
    op.drop_column("settings", "revenue_tax_pct")
    op.drop_column("expenses", "is_recurring")
    op.drop_column("sales", "quote_kind")
```

- [ ] **Step 2: Campos nos models**

`sale.py` — após `client_id` (espelho), adicionar:
```python
    quote_kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="commercial")
```
`expense.py` — após `incurred_at`:
```python
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
```
(garantir `Boolean, false` no import do sqlalchemy em expense.py)
`settings.py` — junto dos numéricos da impressora:
```python
    revenue_tax_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("0"), server_default="0")
```

- [ ] **Step 3: Aplicar e verificar**

Run: `docker compose run --rm api alembic upgrade head`
Expected: aplica `0026_contabil_v2` sem erro. Confirmar com `docker compose run --rm api alembic history | head`.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0026_contabil_v2.py backend/infra/db/models/sale.py backend/infra/db/models/expense.py backend/infra/db/models/settings.py
git commit -m "feat(contabil-v2): migração quote_kind/is_recurring/revenue_tax_pct"
```

---

## Task 2: `sync_sales` inclui pessoais + grava `quote_kind`

**Files:**
- Modify: `backend/core/accounting/sync.py`
- Test: `backend/tests/core/test_accounting_sync.py`

- [ ] **Step 1: Teste**

Acrescentar a `backend/tests/core/test_accounting_sync.py`:

```python
@pytest.mark.asyncio
async def test_sync_includes_personal_with_kind():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="syncp@t.com", password_hash="x")
        s.add(user); await s.commit()
        await _mk_quote(s, user, QuoteStatus.APROVADO, kind=QuoteKind.COMMERCIAL)
        await _mk_quote(s, user, QuoteStatus.PRODUZIDO, kind=QuoteKind.PERSONAL)

    async with session_module.SessionFactory() as s:
        res = await sync_sales(s)
        assert res["created"] == 2
        kinds = {sale.quote_kind for sale in (await s.execute(select(Sale))).scalars().all()}
        assert kinds == {"commercial", "personal"}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_sync.py::test_sync_includes_personal_with_kind -q`
Expected: FAIL — só cria 1 (pessoal ignorado) e/ou `quote_kind` ausente.

- [ ] **Step 3: Implementar**

Em `backend/core/accounting/sync.py`:
- trocar o filtro de kind para incluir os dois:
```python
            select(Quote).where(
                Quote.kind.in_((QuoteKind.COMMERCIAL.value, QuoteKind.PERSONAL.value)),
                Quote.status.in_(ACTIVE_STATUSES),
            )
```
- no upsert, junto dos espelhos, gravar o tipo:
```python
        sale.quote_kind = _status_value(q.kind)
```
(`_status_value` já normaliza StrEnum→str.)

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_sync.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/core/accounting/sync.py backend/tests/core/test_accounting_sync.py
git commit -m "feat(contabil-v2): sync inclui pessoais e grava quote_kind"
```

---

## Task 3: Categoria `equipment` + `is_recurring` no CRUD de despesas

**Files:**
- Modify: `backend/core/models.py`, `backend/api/schemas/accounting.py`, `backend/api/routes/accounting.py`
- Test: `backend/tests/api/test_accounting.py`

- [ ] **Step 1: Teste**

Acrescentar a `backend/tests/api/test_accounting.py`:

```python
@pytest.mark.asyncio
async def test_expense_equipment_and_recurring(auth_client):
    r = await auth_client.post("/accounting/expenses", json={
        "category": "equipment", "description": "Impressora X1", "amount": "3000.00",
        "incurred_at": "2026-06-01", "is_recurring": False,
    })
    assert r.status_code == 201, r.text
    assert r.json()["category"] == "equipment"
    r = await auth_client.post("/accounting/expenses", json={
        "category": "other", "description": "Internet", "amount": "100.00",
        "incurred_at": "2026-06-01", "is_recurring": True,
    })
    assert r.json()["is_recurring"] is True
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py::test_expense_equipment_and_recurring -q`
Expected: FAIL — `equipment` inválido / `is_recurring` desconhecido.

- [ ] **Step 3: Implementar**

`backend/core/models.py` — em `ExpenseCategory`, adicionar:
```python
    EQUIPMENT = "equipment"
```
`backend/api/schemas/accounting.py`:
- `ExpenseCreate`: adicionar `is_recurring: bool = False`.
- `ExpenseUpdate`: adicionar `is_recurring: bool | None = None`.
- `ExpenseOut`: adicionar `is_recurring: bool`.

`backend/api/routes/accounting.py`:
- `_expense_out`: incluir `is_recurring=e.is_recurring`.
- `create_expense`: incluir `is_recurring=payload.is_recurring` no `Expense(...)`.
- (o `update_expense` já aplica via `model_dump(exclude_unset=True)`.)

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/core/models.py backend/api/schemas/accounting.py backend/api/routes/accounting.py backend/tests/api/test_accounting.py
git commit -m "feat(contabil-v2): categoria equipment + is_recurring no CRUD"
```

---

## Task 4: `compute_dre` v2 (custo de estoque, recorrentes, imposto, stale)

**Files:**
- Modify: `backend/core/accounting/dre.py`
- Test: `backend/tests/core/test_accounting_dre.py`

- [ ] **Step 1: Testes**

Substituir/atualizar o teste existente e adicionar casos em `backend/tests/core/test_accounting_dre.py`. O teste v1 (`test_dre_aggregates_sold_sales_and_expenses`) continua válido para os campos antigos; acrescentar:

```python
from datetime import date
from decimal import Decimal
import pytest
from backend.core.accounting.dre import compute_dre
from backend.core.models import ExpenseCategory, QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    Expense, MaterialConsumption, Quote, QuoteItem, Sale, Settings, Spool, User,
)


@pytest.mark.asyncio
async def test_dre_v2_tax_recurring_and_unsold_stock():
    async with session_module.SessionFactory() as s:
        await s.merge(Settings(id=1, revenue_tax_pct=Decimal("10")))
        user = User(name="u", email="drev2@t.com", password_hash="x")
        s.add(user); await s.commit()
        # venda confirmada: receita 1000, cpv 0, variável 0
        q_sold = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                       status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"),
                       min_charge=Decimal("0"))
        # quote produzida não vendida (consumo vira custo de estoque)
        q_unsold = Quote(kind=QuoteKind.PERSONAL.value, user_id=user.id,
                         status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                         min_charge=Decimal("0"))
        s.add_all([q_sold, q_unsold]); await s.commit()
        s.add(Sale(quote_id=q_sold.id, quote_status="entregue", quote_kind="commercial",
                   quote_total=Decimal("1000"), cpv_calc=Decimal("0"), is_sold=True,
                   confirmed_revenue=Decimal("1000"), variable_costs=Decimal("0"),
                   sold_at=date(2026, 6, 10)))
        # consumo do q_unsold em junho: 100 g a R$0,50 = R$50
        item = QuoteItem(quote_id=q_unsold.id, name="p", gcode_meta={}, quantity=1)
        spool = Spool(material_type="PLA", purchased_at=date(2026, 6, 1),
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("900"))
        s.add_all([item, spool]); await s.commit()
        s.add(MaterialConsumption(quote_item_id=item.id, spool_id=spool.id,
                                  grams_used=Decimal("100"), unit_cost_snapshot=Decimal("0.50"),
                                  consumed_at=date(2026, 6, 12)))
        # despesa recorrente de R$100 começando em junho
        s.add(Expense(category=ExpenseCategory.OTHER.value, description="internet",
                      amount=Decimal("100"), incurred_at=date(2026, 6, 1), is_recurring=True))
        await s.commit()

    async with session_module.SessionFactory() as s:
        dre = await compute_dre(s, date(2026, 6, 1), date(2026, 6, 30))

    assert dre["receita_bruta"] == Decimal("1000.00")
    assert dre["impostos"] == Decimal("100.00")            # 10% de 1000
    assert dre["receita_liquida"] == Decimal("900.00")
    assert dre["custo_estoque"] == Decimal("50.00")        # consumo não vendido
    assert dre["despesas"]["other"] == Decimal("100.00")   # recorrente conta no mês de início
    # resultado = 900 - 0(cpv) - 0(var) - (100 desp + 50 estoque) = 750
    assert dre["resultado_liquido"] == Decimal("750.00")


@pytest.mark.asyncio
async def test_dre_recurring_replicates_per_month():
    async with session_module.SessionFactory() as s:
        await s.merge(Settings(id=1, revenue_tax_pct=Decimal("0")))
        s.add(Expense(category=ExpenseCategory.OTHER.value, description="aluguel",
                      amount=Decimal("100"), incurred_at=date(2026, 1, 1), is_recurring=True))
        await s.commit()
    async with session_module.SessionFactory() as s:
        dre = await compute_dre(s, date(2026, 1, 1), date(2026, 3, 31))
    # jan, fev, mar => 3 × 100
    assert dre["despesas"]["other"] == Decimal("300.00")
```

Nota: `consumed_at` é `DateTime(timezone=True)` no model — passar `date(...)` funciona no insert (vira meia-noite). Se o driver reclamar, usar `datetime(2026,6,12, tzinfo=timezone.utc)`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_dre.py -q`
Expected: FAIL — campos `impostos`/`receita_liquida`/`custo_estoque` ausentes; recorrente não replica.

- [ ] **Step 3: Implementar `compute_dre` v2**

Reescrever `backend/core/accounting/dre.py` (mantendo `sale_cpv` e `_q2`):

```python
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import ExpenseCategory
from backend.infra.db.models import (
    Expense, MaterialConsumption, Quote, QuoteItem, Sale, Settings,
)


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


def sale_cpv(sale: Sale) -> Decimal:
    return sale.cpv_override if sale.cpv_override is not None else sale.cpv_calc


def _months(period_from: date, period_to: date) -> list[tuple[int, int]]:
    """Lista de (ano, mês) tocados pelo período, inclusive."""
    out: list[tuple[int, int]] = []
    y, m = period_from.year, period_from.month
    while (y, m) <= (period_to.year, period_to.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1; y += 1
    return out


async def _custo_estoque(session: AsyncSession, period_from: date, period_to: date) -> Decimal:
    """Σ consumo (por consumed_at) cujas quotes NÃO têm venda confirmada ativa."""
    sold_quote_ids = set(
        (await session.execute(
            select(Sale.quote_id).where(Sale.is_sold.is_(True), Sale.is_stale.is_(False))
        )).scalars().all()
    )
    rows = (
        await session.execute(
            select(MaterialConsumption, QuoteItem.quote_id)
            .join(QuoteItem, MaterialConsumption.quote_item_id == QuoteItem.id)
            .where(
                MaterialConsumption.consumed_at >= period_from,
                MaterialConsumption.consumed_at < _next_day(period_to),
            )
        )
    ).all()
    total = Decimal(0)
    for cons, quote_id in rows:
        if quote_id in sold_quote_ids:
            continue
        total += cons.grams_used * cons.unit_cost_snapshot
    return total


def _next_day(d: date) -> date:
    from datetime import timedelta
    return d + timedelta(days=1)


async def compute_dre(session: AsyncSession, period_from: date, period_to: date) -> dict:
    settings_row = await session.get(Settings, 1)
    tax_pct = settings_row.revenue_tax_pct if settings_row else Decimal(0)

    sales = (
        await session.execute(
            select(Sale).where(
                Sale.is_sold.is_(True),
                Sale.is_stale.is_(False),
                Sale.sold_at.is_not(None),
                Sale.sold_at >= period_from,
                Sale.sold_at <= period_to,
            )
        )
    ).scalars().all()

    receita = sum((s.confirmed_revenue or Decimal(0) for s in sales), Decimal(0))
    impostos = receita * tax_pct / Decimal(100)
    receita_liquida = receita - impostos
    cpv = sum((sale_cpv(s) for s in sales), Decimal(0))
    variaveis = sum((s.variable_costs for s in sales), Decimal(0))
    lucro_bruto = receita_liquida - cpv - variaveis

    # despesas: avulsas por incurred_at; recorrentes uma vez por mês do período
    expenses = (await session.execute(select(Expense))).scalars().all()
    months = _months(period_from, period_to)
    despesas = {cat.value: Decimal(0) for cat in ExpenseCategory}
    for e in expenses:
        if e.is_recurring:
            start = (e.incurred_at.year, e.incurred_at.month)
            n = sum(1 for ym in months if ym >= start)
            despesas[e.category] = despesas.get(e.category, Decimal(0)) + e.amount * n
        elif period_from <= e.incurred_at <= period_to:
            despesas[e.category] = despesas.get(e.category, Decimal(0)) + e.amount

    custo_estoque = await _custo_estoque(session, period_from, period_to)
    total_despesas = sum(despesas.values(), Decimal(0)) + custo_estoque

    resultado = lucro_bruto - total_despesas
    margem = (resultado / receita * Decimal(100)) if receita > 0 else Decimal(0)

    return {
        "receita_bruta": _q2(receita),
        "impostos": _q2(impostos),
        "receita_liquida": _q2(receita_liquida),
        "cpv": _q2(cpv),
        "custos_variaveis": _q2(variaveis),
        "lucro_bruto": _q2(lucro_bruto),
        "despesas": {k: _q2(v) for k, v in despesas.items()},
        "custo_estoque": _q2(custo_estoque),
        "total_despesas": _q2(total_despesas),
        "resultado_liquido": _q2(resultado),
        "margem_liquida_pct": _q2(margem),
    }
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_dre.py -q`
Expected: PASS (v1 + os 2 novos).

- [ ] **Step 5: Commit**

```bash
git add backend/core/accounting/dre.py backend/tests/core/test_accounting_dre.py
git commit -m "feat(contabil-v2): compute_dre com imposto, custo de estoque, recorrentes e stale"
```

---

## Task 5: Schemas/rota do DRE e Settings (imposto)

**Files:**
- Modify: `backend/api/schemas/accounting.py` (`DreOut`)
- Modify: `backend/api/schemas/settings.py`, `backend/api/routes/settings.py`
- Test: `backend/tests/api/test_accounting.py`, `backend/tests/api/test_settings.py`

- [ ] **Step 1: Teste**

Em `backend/tests/api/test_accounting.py`, reforçar o shape do DRE v2:
```python
@pytest.mark.asyncio
async def test_dre_v2_shape(auth_client):
    r = await auth_client.get("/accounting/dre?from=2026-06-01&to=2026-06-30")
    assert r.status_code == 200, r.text
    for key in ["impostos", "receita_liquida", "custo_estoque"]:
        assert key in r.json()
```
Em `backend/tests/api/test_settings.py`, conferir que `revenue_tax_pct` é aceito:
```python
@pytest.mark.asyncio
async def test_settings_revenue_tax(auth_client):
    r = await auth_client.put("/settings", json={"revenue_tax_pct": "6.00"})
    assert r.status_code == 200, r.text
    assert r.json()["revenue_tax_pct"] == "6.00"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py::test_dre_v2_shape backend/tests/api/test_settings.py::test_settings_revenue_tax -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

`DreOut` em `accounting.py` — adicionar campos: `impostos: Decimal`, `receita_liquida: Decimal`, `custo_estoque: Decimal` (mantendo os v1).
`SettingsIn`: `revenue_tax_pct: Decimal | None = None`. `SettingsOut`: `revenue_tax_pct: Decimal`. O `_out` em `routes/settings.py` inclui `revenue_tax_pct=s.revenue_tax_pct`.

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py backend/tests/api/test_settings.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/schemas/accounting.py backend/api/schemas/settings.py backend/api/routes/settings.py backend/tests/api/test_accounting.py backend/tests/api/test_settings.py
git commit -m "feat(contabil-v2): DreOut v2 + revenue_tax_pct em Settings"
```

---

## Task 6: Dashboard alinhado (stale, custo de estoque, imposto)

**Files:**
- Modify: `backend/api/routes/dashboard.py`
- Test: `backend/tests/api/test_dashboard.py`

- [ ] **Step 1: Teste**

Acrescentar a `backend/tests/api/test_dashboard.py` um caso que cria uma venda confirmada com `revenue_tax_pct=10` e confere que `lucro` desconta imposto e `despesa` soma custo de estoque (seguir o padrão de seed do `test_dashboard_receita_from_confirmed_sale`, criando também uma `MaterialConsumption` não vendida e setando `Settings.revenue_tax_pct`). Asserções-chave:
```python
    # receita 777, imposto 10% => 77.70; sem custos de venda; estoque não vendido 20
    assert body["cards"]["receita"] == "777.00"
    # despesa = custo de estoque (20.00); lucro = 777 - 77.70(imposto) - 20 = 679.30
    assert body["cards"]["despesa"] == "20.00"
    assert body["cards"]["lucro"] == "679.30"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_dashboard.py -q`
Expected: FAIL no caso novo.

- [ ] **Step 3: Implementar**

Em `backend/api/routes/dashboard.py`:
- importar o helper de custo de estoque e o imposto: reusar `compute_dre`? Não — o dashboard tem charts próprios. Em vez de duplicar, importar as funções de `dre.py`:
```python
from backend.core.accounting.dre import sale_cpv, _custo_estoque
```
- na query `confirmed`, adicionar `Sale.is_stale.is_(False)`.
- após calcular `despesa_vendas`/`despesa_ops`, somar custo de estoque e descontar imposto:
```python
    custo_estoque = await _custo_estoque(session, pf_date, pt_date)
    despesa = despesa_vendas + despesa_ops + custo_estoque
    settings_tax = (await session.get(Settings, 1))
    tax_pct = settings_tax.revenue_tax_pct if settings_tax else Decimal(0)
    impostos = receita * tax_pct / Decimal(100)
```
- ajustar `lucro = receita - despesa - impostos`.
- no gráfico `rev_exp_buckets`, somar `custo_estoque` no bucket do período (uma entrada agregada é aceitável; ou distribuir por `consumed_at`). Para simplicidade, somar `custo_estoque` na despesa do bucket do `pt_date` mês.

(Confirmar que `_custo_estoque` é importável — se preferir não importar um nome com underscore, renomear para `custo_estoque_periodo` público em `dre.py` e atualizar ambos os call sites.)

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_dashboard.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/dashboard.py backend/tests/api/test_dashboard.py
git commit -m "feat(dashboard): alinhar com DRE v2 (stale, custo de estoque, imposto)"
```

---

## Task 7: Frontend — tipo de venda, recorrente, imposto, linhas novas do DRE

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/routes/accounting/+page.svelte`, `frontend/src/routes/settings/+page.svelte`

- [ ] **Step 1: Tipos**

Em `types.ts`: `Sale` ganha `quote_kind: string`; `Expense`/CRUD ganham `is_recurring: boolean`; `ExpenseCategory` inclui `"equipment"`; `Dre` ganha `impostos`, `receita_liquida`, `custo_estoque` (strings).

- [ ] **Step 2: Aba Vendas — coluna/filtro tipo**

Na tabela de vendas, adicionar coluna "Tipo" (`quote_kind` → "Comercial"/"Pessoal" via um `fmtKind`) e, opcionalmente, um filtro. Reaproveitar o `CATS` para o select e adicionar `{ value: "equipment", label: "Máquinas/Equipamentos" }`.

- [ ] **Step 3: Despesas — checkbox recorrente**

No form de criar despesa, um checkbox "recorrente (mensal)" ligado a uma var `exRecurring`, enviado no POST. Mostrar na tabela uma marca quando `is_recurring`.

- [ ] **Step 4: DRE — linhas novas**

No demonstrativo, inserir após a receita bruta: "(−) Impostos" e "= Receita líquida"; e no bloco de despesas a linha "Custo de estoque (não vendido)" (`dre.custo_estoque`).

- [ ] **Step 5: Settings — campo imposto**

Em `routes/settings/+page.svelte`, adicionar um input "Imposto sobre receita (%)" ligado a `revenue_tax_pct`, no mesmo padrão dos demais campos numéricos.

- [ ] **Step 6: Check**

Run: `cd frontend && npm run check`
Expected: sem erros novos.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/routes/accounting/+page.svelte frontend/src/routes/settings/+page.svelte
git commit -m "feat(contabil-v2): UI tipo de venda, recorrente, imposto e linhas do DRE"
```

---

## Task 8: Verificação

- [ ] **Step 1:** `docker compose run --rm api pytest backend/tests -q` → tudo PASS.
- [ ] **Step 2:** `cd frontend && npm run check` → sem erros novos.
- [ ] **Step 3:** `docker compose run --rm api ruff check backend/core/accounting backend/api/routes/dashboard.py backend/api/routes/accounting.py` → sem erros novos.

---

## Notas

- **`_custo_estoque`/`sale_cpv` compartilhados:** o dashboard importa de `dre.py` para usar a mesma regra. Se preferir nomes públicos, promova `_custo_estoque` → `custo_estoque_periodo` e ajuste os dois call sites.
- **Atribuição temporal:** custo de estoque por `consumed_at`, vendas por `sold_at` — divergência de eixo aceita (spec §4, nota de simplificação).
