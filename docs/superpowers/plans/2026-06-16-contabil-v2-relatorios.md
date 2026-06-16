# Contábil v2 — relatórios — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DRE mês a mês (visão planilhada), lucratividade por cliente/material e exportação XLSX com os dados brutos.

**Architecture:** Reusa o `compute_dre` v2 por mês para a visão mensal; um módulo de lucratividade rateia receita/custo por material; um gerador XLSX (`openpyxl`) monta as abas. Tudo em rotas novas sob `/accounting`.

**Tech Stack:** FastAPI + SQLAlchemy async, `openpyxl` (nova dep), pytest via Docker, SvelteKit.

**Spec:** `docs/superpowers/specs/2026-06-16-contabil-v2-relatorios-design.md`
**Depende do plano:** `2026-06-16-contabil-v2-dre.md` (compute_dre v2 + `quote_kind`).

---

## File Structure

- `pyproject.toml` — adicionar `openpyxl`.
- `backend/core/accounting/monthly.py` — `compute_dre_monthly`.
- `backend/core/accounting/profitability.py` — `compute_profitability` (por cliente e material).
- `backend/core/accounting/export_xlsx.py` — `build_dre_xlsx` (bytes).
- `backend/api/schemas/accounting.py` — `MonthlyDreOut`, `ProfitabilityOut`.
- `backend/api/routes/accounting.py` — rotas `/dre/monthly`, `/profitability`, `/dre/export.xlsx`.
- `frontend`: `lib/types.ts`, `routes/accounting/+page.svelte` (toggle mensal, lucratividade, botão exportar).

---

## Task 1: Dependência `openpyxl`

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Adicionar a dep**

Em `pyproject.toml`, na lista de dependências do projeto, acrescentar `"openpyxl>=3.1"`.

- [ ] **Step 2: Rebuild da imagem e verificar import**

Run: `docker compose build api`
Run: `docker compose run --rm api python -c "import openpyxl; print(openpyxl.__version__)"`
Expected: imprime a versão sem erro.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: adiciona openpyxl para export XLSX"
```

---

## Task 2: DRE mensal

**Files:**
- Create: `backend/core/accounting/monthly.py`
- Modify: `backend/api/schemas/accounting.py`, `backend/api/routes/accounting.py`
- Test: `backend/tests/core/test_accounting_monthly.py` (novo), `backend/tests/api/test_accounting.py`

- [ ] **Step 1: Teste do core**

`backend/tests/core/test_accounting_monthly.py`:

```python
from datetime import date
import pytest
from backend.core.accounting.monthly import compute_dre_monthly
from backend.infra.db import session as session_module


@pytest.mark.asyncio
async def test_monthly_returns_one_per_month():
    async with session_module.SessionFactory() as s:
        rows = await compute_dre_monthly(s, date(2026, 1, 1), date(2026, 3, 31))
    assert [r["month"] for r in rows] == ["2026-01", "2026-02", "2026-03"]
    for r in rows:
        assert "resultado_liquido" in r
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_monthly.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

`backend/core/accounting/monthly.py`:

```python
from calendar import monthrange
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.accounting.dre import compute_dre


def _month_iter(period_from: date, period_to: date):
    y, m = period_from.year, period_from.month
    while (y, m) <= (period_to.year, period_to.month):
        start = date(y, m, 1)
        end = date(y, m, monthrange(y, m)[1])
        yield f"{y:04d}-{m:02d}", start, end
        m += 1
        if m > 12:
            m = 1; y += 1


async def compute_dre_monthly(session: AsyncSession, period_from: date, period_to: date) -> list[dict]:
    out: list[dict] = []
    for label, start, end in _month_iter(period_from, period_to):
        dre = await compute_dre(session, start, end)
        out.append({"month": label, **dre})
    return out
```

- [ ] **Step 4: Rota + schema**

`MonthlyDreOut` em `accounting.py` schemas: `month: str` + os campos do `DreOut` (pode ser `class MonthlyDreOut(DreOut): month: str`). Rota em `routes/accounting.py`:

```python
@router.get("/dre/monthly", response_model=list[MonthlyDreOut])
async def dre_monthly(
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
    from_: date = Query(..., alias="from"), to: date = Query(...),
):
    return [MonthlyDreOut(**row) for row in await compute_dre_monthly(session, from_, to)]
```

- [ ] **Step 5: Teste de API**

Em `backend/tests/api/test_accounting.py`:
```python
@pytest.mark.asyncio
async def test_dre_monthly_shape(auth_client):
    r = await auth_client.get("/accounting/dre/monthly?from=2026-01-01&to=2026-02-28")
    assert r.status_code == 200, r.text
    assert [x["month"] for x in r.json()] == ["2026-01", "2026-02"]
```

- [ ] **Step 6: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_monthly.py backend/tests/api/test_accounting.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/core/accounting/monthly.py backend/api/schemas/accounting.py backend/api/routes/accounting.py backend/tests/core/test_accounting_monthly.py backend/tests/api/test_accounting.py
git commit -m "feat(contabil-v2): DRE mensal"
```

---

## Task 3: Lucratividade por cliente/material

**Files:**
- Create: `backend/core/accounting/profitability.py`
- Modify: `backend/api/schemas/accounting.py`, `backend/api/routes/accounting.py`
- Test: `backend/tests/core/test_accounting_profitability.py` (novo)

- [ ] **Step 1: Teste**

`backend/tests/core/test_accounting_profitability.py`:

```python
from datetime import date
from decimal import Decimal
import pytest
from backend.core.accounting.profitability import compute_profitability
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    Client, MaterialVersion, Quote, QuoteItem, Sale, User,
)


@pytest.mark.asyncio
async def test_profitability_by_client_and_material():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="prof@t.com", password_hash="x")
        cli = Client(name="Ana")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"))
        s.add_all([user, cli, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id, client_id=cli.id,
                  status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"), min_charge=Decimal("0"))
        s.add(q); await s.commit()
        s.add(QuoteItem(quote_id=q.id, name="p", gcode_meta={"filament_m": 10},
                        material_version_id=mv.id, quantity=1))
        s.add(Sale(quote_id=q.id, quote_status="entregue", quote_kind="commercial",
                   quote_total=Decimal("200"), cpv_calc=Decimal("50"), is_sold=True, is_stale=False,
                   confirmed_revenue=Decimal("200"), variable_costs=Decimal("0"),
                   client_id=cli.id, sold_at=date(2026, 6, 10)))
        await s.commit()

    async with session_module.SessionFactory() as s:
        prof = await compute_profitability(s, date(2026, 6, 1), date(2026, 6, 30))

    by_client = {r["label"]: r for r in prof["by_client"]}
    assert by_client["Ana"]["receita"] == Decimal("200.00")
    assert by_client["Ana"]["margem"] == Decimal("150.00")  # 200 - 50
    by_mat = {r["label"]: r for r in prof["by_material"]}
    assert by_mat["PLA"]["receita"] == Decimal("200.00")  # único material -> 100% rateio
    assert by_mat["PLA"]["margem"] == Decimal("150.00")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_profitability.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

`backend/core/accounting/profitability.py`:

```python
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.accounting.cost import _DIAMETER_MM
from backend.core.accounting.dre import sale_cpv
from backend.core.pricing.cost import grams_from_meters, filament_cost
from backend.infra.db.models import Client, MaterialVersion, QuoteItem, Sale


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


def _rows(agg: dict[str, dict]) -> list[dict]:
    out = []
    for label, v in agg.items():
        receita, custo = v["receita"], v["custo"]
        margem = receita - custo
        pct = (margem / receita * Decimal(100)) if receita > 0 else Decimal(0)
        out.append({"label": label, "receita": _q2(receita), "custo": _q2(custo),
                    "margem": _q2(margem), "margem_pct": _q2(pct)})
    out.sort(key=lambda r: r["margem"], reverse=True)
    return out


async def compute_profitability(session: AsyncSession, period_from: date, period_to: date) -> dict:
    sales = (
        await session.execute(
            select(Sale).where(
                Sale.is_sold.is_(True), Sale.is_stale.is_(False),
                Sale.sold_at.is_not(None),
                Sale.sold_at >= period_from, Sale.sold_at <= period_to,
            )
        )
    ).scalars().all()

    by_client: dict[str, dict] = {}
    by_material: dict[str, dict] = {}

    for sale in sales:
        receita = sale.confirmed_revenue or Decimal(0)
        custo = sale_cpv(sale) + sale.variable_costs

        # por cliente
        cname = "—"
        if sale.client_id:
            c = await session.get(Client, sale.client_id)
            cname = c.name if c else "—"
        slot = by_client.setdefault(cname, {"receita": Decimal(0), "custo": Decimal(0)})
        slot["receita"] += receita; slot["custo"] += custo

        # por material — rateio pelo custo de filamento de cada item
        items = (await session.execute(
            select(QuoteItem).where(QuoteItem.quote_id == sale.quote_id))).scalars().all()
        shares: list[tuple[str, Decimal]] = []
        for it in items:
            mt = "—"; fcost = Decimal(0)
            if it.material_version_id:
                mv = await session.get(MaterialVersion, it.material_version_id)
                if mv:
                    mt = mv.material_type
                    grams = grams_from_meters(float(it.gcode_meta.get("filament_m", 0) or 0),
                                              mv.density_g_cm3, _DIAMETER_MM) * Decimal(it.quantity)
                    fcost = filament_cost(grams, mv.price_per_kg_ref)
            shares.append((mt, fcost))
        total_share = sum((c for _, c in shares), Decimal(0))
        if total_share <= 0:
            slot = by_material.setdefault("—", {"receita": Decimal(0), "custo": Decimal(0)})
            slot["receita"] += receita; slot["custo"] += custo
        else:
            for mt, fcost in shares:
                frac = fcost / total_share
                slot = by_material.setdefault(mt, {"receita": Decimal(0), "custo": Decimal(0)})
                slot["receita"] += receita * frac; slot["custo"] += custo * frac

    return {"by_client": _rows(by_client), "by_material": _rows(by_material)}
```

(Se `_DIAMETER_MM` não estiver exportável de `cost.py`, redefinir localmente `Decimal("1.75")`.)

- [ ] **Step 4: Rota + schema**

Schemas: `ProfitabilityRow` (`label, receita, custo, margem, margem_pct: Decimal`) e
`ProfitabilityOut` (`by_client: list[ProfitabilityRow]`, `by_material: list[ProfitabilityRow]`).
Rota:
```python
@router.get("/profitability", response_model=ProfitabilityOut)
async def profitability(
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
    from_: date = Query(..., alias="from"), to: date = Query(...),
):
    return ProfitabilityOut(**await compute_profitability(session, from_, to))
```

- [ ] **Step 5: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_profitability.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/accounting/profitability.py backend/api/schemas/accounting.py backend/api/routes/accounting.py backend/tests/core/test_accounting_profitability.py
git commit -m "feat(contabil-v2): lucratividade por cliente e material"
```

---

## Task 4: Exportação XLSX

**Files:**
- Create: `backend/core/accounting/export_xlsx.py`
- Modify: `backend/api/routes/accounting.py`
- Test: `backend/tests/api/test_accounting.py`

- [ ] **Step 1: Teste**

Em `backend/tests/api/test_accounting.py`:

```python
@pytest.mark.asyncio
async def test_dre_export_xlsx(auth_client):
    import io
    from openpyxl import load_workbook
    r = await auth_client.get("/accounting/dre/export.xlsx?from=2026-06-01&to=2026-06-30")
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers["content-type"]
    wb = load_workbook(io.BytesIO(r.content))
    assert {"DRE mensal", "Vendas", "Despesas", "Custo de estoque", "Lucratividade"} <= set(wb.sheetnames)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py::test_dre_export_xlsx -q`
Expected: FAIL — 404.

- [ ] **Step 3: Implementar o gerador**

`backend/core/accounting/export_xlsx.py` — função `async def build_dre_xlsx(session, period_from, period_to) -> bytes` que monta um `openpyxl.Workbook` com as abas:
- `DRE mensal`: cabeçalho `Conta | <meses...> | Total`; linhas para Receita bruta, Impostos, Receita líquida, CPV, Custos variáveis, Lucro bruto, cada categoria de despesa (rótulo PT), Custo de estoque, Resultado líquido, Margem %. Valores via `compute_dre_monthly`; coluna Total = `compute_dre(period_from, period_to)`.
- `Vendas`: linhas das vendas confirmadas ativas no período (orçamento, tipo `quote_kind`, cliente, status, total, CPV, receita, variáveis, data).
- `Despesas`: lançamentos do período (categoria, descrição, valor, recorrente, data).
- `Custo de estoque`: linhas de `MaterialConsumption` contadas (gramas, custo unitário, total, data, quote_id).
- `Lucratividade`: as duas tabelas de `compute_profitability` (cliente e material).
Retornar `wb` salvo em `io.BytesIO` → `.getvalue()`.

Mostrar o esqueleto (o engenheiro preenche as linhas seguindo os helpers já existentes — `compute_dre_monthly`, `compute_dre`, `compute_profitability`, e queries diretas para as abas de dados brutos):

```python
import io
from datetime import date
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.accounting.dre import compute_dre
from backend.core.accounting.monthly import compute_dre_monthly
from backend.core.accounting.profitability import compute_profitability
from backend.core.models import ExpenseCategory
from backend.infra.db.models import Expense, MaterialConsumption, QuoteItem, Sale

_CAT_LABEL = {"maintenance": "Manutenção", "parts": "Peças", "tools": "Ferramentas",
              "labor": "Mecânicos", "equipment": "Máquinas/Equipamentos", "other": "Outros"}


async def build_dre_xlsx(session: AsyncSession, period_from: date, period_to: date) -> bytes:
    wb = Workbook()

    # --- DRE mensal ---
    ws = wb.active
    ws.title = "DRE mensal"
    monthly = await compute_dre_monthly(session, period_from, period_to)
    total = await compute_dre(session, period_from, period_to)
    months = [m["month"] for m in monthly]
    ws.append(["Conta", *months, "Total"])
    def line(label, key):
        ws.append([label, *[float(m[key]) for m in monthly], float(total[key])])
    line("Receita bruta", "receita_bruta")
    line("(-) Impostos", "impostos")
    line("= Receita líquida", "receita_liquida")
    line("(-) CPV", "cpv")
    line("(-) Custos variáveis", "custos_variaveis")
    line("= Lucro bruto", "lucro_bruto")
    for cat in ExpenseCategory:
        ws.append([f"(-) {_CAT_LABEL[cat.value]}",
                   *[float(m["despesas"][cat.value]) for m in monthly],
                   float(total["despesas"][cat.value])])
    line("(-) Custo de estoque", "custo_estoque")
    line("= Resultado líquido", "resultado_liquido")
    line("Margem líquida %", "margem_liquida_pct")

    # --- Vendas ---
    ws = wb.create_sheet("Vendas")
    ws.append(["Orçamento", "Tipo", "Status", "Total", "CPV", "Receita", "Variáveis", "Data"])
    sales = (await session.execute(select(Sale).where(
        Sale.is_sold.is_(True), Sale.is_stale.is_(False),
        Sale.sold_at >= period_from, Sale.sold_at <= period_to))).scalars().all()
    for s in sales:
        ws.append([str(s.quote_id), s.quote_kind, s.quote_status, float(s.quote_total),
                   float(s.cpv_calc), float(s.confirmed_revenue or 0), float(s.variable_costs),
                   s.sold_at.isoformat() if s.sold_at else ""])

    # --- Despesas ---
    ws = wb.create_sheet("Despesas")
    ws.append(["Categoria", "Descrição", "Valor", "Recorrente", "Data"])
    exps = (await session.execute(select(Expense).where(
        Expense.incurred_at >= period_from, Expense.incurred_at <= period_to))).scalars().all()
    for e in exps:
        ws.append([_CAT_LABEL.get(e.category, e.category), e.description, float(e.amount),
                   "sim" if e.is_recurring else "não", e.incurred_at.isoformat()])

    # --- Custo de estoque ---
    ws = wb.create_sheet("Custo de estoque")
    ws.append(["Orçamento", "Gramas", "Custo unit.", "Total", "Data"])
    rows = (await session.execute(
        select(MaterialConsumption, QuoteItem.quote_id)
        .join(QuoteItem, MaterialConsumption.quote_item_id == QuoteItem.id)
        .where(MaterialConsumption.consumed_at >= period_from))).all()
    for cons, qid in rows:
        ws.append([str(qid), float(cons.grams_used), float(cons.unit_cost_snapshot),
                   float(cons.grams_used * cons.unit_cost_snapshot),
                   cons.consumed_at.date().isoformat() if cons.consumed_at else ""])

    # --- Lucratividade ---
    ws = wb.create_sheet("Lucratividade")
    prof = await compute_profitability(session, period_from, period_to)
    ws.append(["Por cliente", "Receita", "Custo", "Margem", "Margem %"])
    for r in prof["by_client"]:
        ws.append([r["label"], float(r["receita"]), float(r["custo"]), float(r["margem"]), float(r["margem_pct"])])
    ws.append([])
    ws.append(["Por material", "Receita", "Custo", "Margem", "Margem %"])
    for r in prof["by_material"]:
        ws.append([r["label"], float(r["receita"]), float(r["custo"]), float(r["margem"]), float(r["margem_pct"])])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Rota**

Em `routes/accounting.py`:
```python
from fastapi.responses import StreamingResponse
from backend.core.accounting.export_xlsx import build_dre_xlsx

@router.get("/dre/export.xlsx")
async def dre_export(
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
    from_: date = Query(..., alias="from"), to: date = Query(...),
):
    data = await build_dre_xlsx(session, from_, to)
    headers = {"Content-Disposition": f'attachment; filename="dre_{from_}_{to}.xlsx"'}
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )
```

- [ ] **Step 5: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py::test_dre_export_xlsx -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/accounting/export_xlsx.py backend/api/routes/accounting.py backend/tests/api/test_accounting.py
git commit -m "feat(contabil-v2): exportação XLSX do DRE com dados brutos"
```

---

## Task 5: Frontend — mensal, lucratividade, exportar

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/routes/accounting/+page.svelte`

- [ ] **Step 1: Tipos**

`types.ts`: `MonthlyDre = Dre & { month: string }`; `ProfitabilityRow = { label: string; receita: string; custo: string; margem: string; margem_pct: string }`; `Profitability = { by_client: ProfitabilityRow[]; by_material: ProfitabilityRow[] }`.

- [ ] **Step 2: DRE — toggle Período/Mensal**

Na aba DRE, um toggle. Em "Mensal", buscar `api<MonthlyDre[]>("/accounting/dre/monthly?from=&to=")` e montar uma `<table>` com colunas = meses + Total, linhas = contas (Receita bruta, Impostos, Receita líquida, CPV, Variáveis, Lucro bruto, categorias, Custo de estoque, Resultado, Margem). Calcular a coluna Total somando os meses (ou um fetch extra ao `/accounting/dre`).

- [ ] **Step 3: Lucratividade**

Nova sub-aba ou seção: busca `api<Profitability>("/accounting/profitability?from=&to=")` e renderiza duas tabelas (cliente e material) ordenadas por margem, mostrando receita/custo/margem/margem_pct.

- [ ] **Step 4: Botão exportar XLSX**

Na aba DRE, um botão "Exportar XLSX" que faz `window.open(`/api/accounting/dre/export.xlsx?from=${from}&to=${to}`, "_blank")` (download direto; a sessão vai pelo cookie same-origin via proxy/`/api`).

- [ ] **Step 5: Check**

Run: `cd frontend && npm run check`
Expected: sem erros novos.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/routes/accounting/+page.svelte
git commit -m "feat(contabil-v2): UI DRE mensal, lucratividade e exportar XLSX"
```

---

## Task 6: Verificação

- [ ] **Step 1:** `docker compose run --rm api pytest backend/tests -q` → tudo PASS.
- [ ] **Step 2:** `cd frontend && npm run check` → sem erros novos.
- [ ] **Step 3:** `docker compose run --rm api ruff check backend/core/accounting backend/api/routes/accounting.py` → sem erros novos.

---

## Notas

- **Download autenticado:** o XLSX é baixado via `/api/...` same-origin, então o cookie de sessão acompanha. Se o ambiente servir o frontend separado, trocar por fetch+blob com `credentials: "include"`.
- **`compute_dre_monthly` reusa `compute_dre`** — qualquer ajuste no DRE reflete automaticamente no mensal e no XLSX (DRY).
