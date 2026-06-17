# Contábil — tabela fato por item — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expor os dados da Contábil a nível de item (uma linha por venda × item: nome, quantidade, cor da bobina consumida, material, gramas, custo, receita rateada), via endpoint + aba XLSX, e mostrar os nomes dos itens (pipe) na aba Vendas.

**Architecture:** Um builder único `compute_facts` (view computada, sem tabela nova) gera as linhas por item; um helper `sale_items_label` formata a coluna Itens da aba Vendas; ambos compartilham `_item_details`. Reusa `sale_cpv`, `effective_grams_per_unit`, `filament_cost`. Sem mudança no DRE (compra de material descartada — competência puro).

**Tech Stack:** FastAPI + SQLAlchemy async, openpyxl, pytest via `docker compose run --rm api pytest …`, SvelteKit (`cd frontend && npm run check`).

**Spec:** `docs/superpowers/specs/2026-06-17-contabil-fato-itens-design.md`

---

## File Structure

- `backend/core/accounting/facts.py` — `_item_details`, `compute_facts`, `sale_items_label`.
- `backend/api/schemas/accounting.py` — `FactRow`; `SaleOut.itens_label`.
- `backend/api/routes/accounting.py` — rota `/facts`; `list_sales`/`_sale_out` populam `itens_label`.
- `backend/core/accounting/export_xlsx.py` — aba `Fato (itens)`.
- `frontend/src/lib/types.ts`, `frontend/src/routes/accounting/+page.svelte` — coluna Itens.
- Testes: `backend/tests/core/test_accounting_facts.py`, `backend/tests/api/test_accounting.py`, `frontend`.

---

## Task 1: `compute_facts` + `_item_details`

**Files:**
- Create: `backend/core/accounting/facts.py`
- Test: `backend/tests/core/test_accounting_facts.py`

- [ ] **Step 1: Escrever o teste**

`backend/tests/core/test_accounting_facts.py`:

```python
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.core.accounting.facts import compute_facts
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    Client, MaterialConsumption, MaterialVersion, Quote, QuoteItem, Sale, Spool, User,
)


@pytest.mark.asyncio
async def test_facts_item_grain_color_and_revenue_split():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="facts@t.com", password_hash="x")
        cli = Client(name="Ana")
        mv = MaterialVersion(material_type="PLA", name="PLA", color="Azul",
                             density_g_cm3=Decimal("1.24"), price_per_kg_ref=Decimal("100"))
        s.add_all([user, cli, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id, client_id=cli.id,
                  status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"), min_charge=Decimal("0"))
        s.add(q); await s.commit()
        # item 1: gramas override 50 (custo 5,00); item 2: gramas override 50 (custo 5,00)
        it1 = QuoteItem(quote_id=q.id, name="Vaso", gcode_meta={"filament_g": 50},
                        material_version_id=mv.id, quantity=2)
        it2 = QuoteItem(quote_id=q.id, name="Suporte", gcode_meta={"filament_g": 50},
                        material_version_id=mv.id, quantity=1)
        spool = Spool(material_type="PLA", color="Verde", purchased_at=datetime.now(timezone.utc),
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("900"))
        s.add_all([it1, it2, spool]); await s.commit()
        # baixa real só do item 1, da bobina Verde
        s.add(MaterialConsumption(quote_item_id=it1.id, spool_id=spool.id,
                                  grams_used=Decimal("100"), unit_cost_snapshot=Decimal("0.50"),
                                  consumed_at=datetime.now(timezone.utc)))
        s.add(Sale(quote_id=q.id, quote_status="entregue", quote_kind="commercial",
                   quote_total=Decimal("300"), cpv_calc=Decimal("50"), is_sold=True, is_stale=False,
                   confirmed_revenue=Decimal("300"), variable_costs=Decimal("0"),
                   client_id=cli.id, sold_at=date(2026, 6, 10)))
        await s.commit()

    async with session_module.SessionFactory() as s:
        rows = await compute_facts(s, date(2026, 6, 1), date(2026, 6, 30))

    assert len(rows) == 2  # uma linha por item
    by_name = {r["nome"]: r for r in rows}
    vaso = by_name["Vaso"]; sup = by_name["Suporte"]
    # venda repetida
    assert vaso["receita_venda"] == Decimal("300.00")
    assert vaso["cliente"] == "Ana"
    # item: gramas_total = 50 * qty; custo = gramas/1000 * 100
    assert vaso["quantidade"] == 2
    assert vaso["gramas_total"] == Decimal("100.00")           # 50 * 2
    assert vaso["custo_filamento_item"] == Decimal("10.00")    # 100g a R$100/kg
    assert sup["gramas_total"] == Decimal("50.00")
    assert sup["custo_filamento_item"] == Decimal("5.00")
    # cor: item 1 tem bobina Verde; item 2 não produzido -> cor_bobina nula, cor_material Azul
    assert vaso["cor_bobina"] == "Verde"
    assert sup["cor_bobina"] is None
    assert sup["cor_material"] == "Azul"
    # receita_item rateada por custo de filamento (10 vs 5 => 200 / 100) e soma = 300
    assert vaso["receita_item"] == Decimal("200.00")
    assert sup["receita_item"] == Decimal("100.00")
    assert vaso["receita_item"] + sup["receita_item"] == Decimal("300.00")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_facts.py -q`
Expected: FAIL — `ModuleNotFoundError: backend.core.accounting.facts`.

- [ ] **Step 3: Implementar**

`backend/core/accounting/facts.py`:

```python
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.accounting.dre import sale_cpv
from backend.core.pricing.cost import filament_cost
from backend.core.quote_service import effective_grams_per_unit
from backend.infra.db.models import (
    Client, MaterialConsumption, MaterialVersion, QuoteItem, Sale, Spool,
)

_DIAMETER_MM = Decimal("1.75")


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


async def _item_details(session: AsyncSession, it: QuoteItem) -> dict:
    """Campos por item: material/cor, gramas efetivas, custo de filamento, cor da bobina."""
    material_type = "—"
    cor_material = None
    custo = Decimal(0)
    gramas_total = Decimal(0)
    mv = None
    if it.material_version_id:
        mv = await session.get(MaterialVersion, it.material_version_id)
    filament_m = it.gcode_meta.get("filament_m")
    raw_g = it.gcode_meta.get("filament_g")
    filament_g = float(raw_g) if raw_g not in (None, "") else None
    if mv is not None:
        material_type = mv.material_type
        cor_material = mv.color
        grams_unit = effective_grams_per_unit(
            float(filament_m or 0), filament_g, mv.density_g_cm3, _DIAMETER_MM, Decimal("0")
        )
        gramas_total = grams_unit * Decimal(it.quantity)
        custo = filament_cost(gramas_total, mv.price_per_kg_ref)

    # cor da bobina consumida (pipe-join de cores distintas)
    cons_rows = (
        await session.execute(
            select(Spool.color)
            .join(MaterialConsumption, MaterialConsumption.spool_id == Spool.id)
            .where(MaterialConsumption.quote_item_id == it.id)
        )
    ).scalars().all()
    cores = sorted({c for c in cons_rows if c})
    cor_bobina = " | ".join(cores) if cores else None

    return {
        "item_id": str(it.id),
        "nome": it.name,
        "quantidade": it.quantity,
        "material_type": material_type,
        "cor_material": cor_material,
        "cor_bobina": cor_bobina,
        "filament_m": float(filament_m) if filament_m not in (None, "") else None,
        "filament_g": filament_g,
        "gramas_total": _q2(gramas_total),
        "custo_filamento_item": _q2(custo),
    }


async def compute_facts(session: AsyncSession, period_from: date, period_to: date) -> list[dict]:
    """Uma linha por (venda confirmada ativa × item do orçamento)."""
    sales = (
        await session.execute(
            select(Sale).where(
                Sale.is_sold.is_(True), Sale.is_stale.is_(False),
                Sale.sold_at.is_not(None),
                Sale.sold_at >= period_from, Sale.sold_at <= period_to,
            )
        )
    ).scalars().all()

    out: list[dict] = []
    for sale in sales:
        receita = sale.confirmed_revenue or Decimal(0)
        cpv = sale_cpv(sale)
        cname = "—"
        if sale.client_id:
            c = await session.get(Client, sale.client_id)
            cname = c.name if c else "—"

        items = (await session.execute(
            select(QuoteItem).where(QuoteItem.quote_id == sale.quote_id))).scalars().all()
        details = [await _item_details(session, it) for it in items]

        total_fcost = sum((d["custo_filamento_item"] for d in details), Decimal(0))
        n = len(details)
        for d in details:
            if total_fcost > 0:
                receita_item = receita * d["custo_filamento_item"] / total_fcost
            elif n > 0:
                receita_item = receita / Decimal(n)
            else:
                receita_item = Decimal(0)
            out.append({
                "sale_id": str(sale.id),
                "quote_id": str(sale.quote_id),
                "quote_kind": sale.quote_kind,
                "cliente": cname,
                "status": sale.quote_status,
                "sold_at": sale.sold_at,
                "is_sold": sale.is_sold,
                "receita_venda": _q2(receita),
                "custos_variaveis_venda": _q2(sale.variable_costs),
                "cpv_venda": _q2(cpv),
                **d,
                "receita_item": _q2(receita_item),
            })
    return out


async def sale_items_label(session: AsyncSession, sale: Sale) -> str:
    """Rótulo pipe dos itens de uma venda: 'Vaso ×2 (Verde) | Suporte ×1 (Azul)'."""
    items = (await session.execute(
        select(QuoteItem).where(QuoteItem.quote_id == sale.quote_id))).scalars().all()
    parts: list[str] = []
    for it in items:
        d = await _item_details(session, it)
        cor = d["cor_bobina"] or d["cor_material"]
        suffix = f" ({cor})" if cor else ""
        parts.append(f"{d['nome']} ×{d['quantidade']}{suffix}")
    return " | ".join(parts)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_facts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/accounting/facts.py backend/tests/core/test_accounting_facts.py
git commit -m "feat(contabil): compute_facts (tabela fato por item) + sale_items_label"
```

---

## Task 2: Endpoint `/accounting/facts`

**Files:**
- Modify: `backend/api/schemas/accounting.py`, `backend/api/routes/accounting.py`
- Test: `backend/tests/api/test_accounting.py`

- [ ] **Step 1: Teste**

Acrescentar a `backend/tests/api/test_accounting.py`:

```python
@pytest.mark.asyncio
async def test_facts_endpoint_shape(auth_client):
    r = await auth_client.get("/accounting/facts?from=2026-06-01&to=2026-06-30")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py::test_facts_endpoint_shape -q`
Expected: FAIL — 404.

- [ ] **Step 3: Schema + rota**

Em `backend/api/schemas/accounting.py`, adicionar:

```python
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
```

Em `backend/api/routes/accounting.py`: importar `compute_facts` e `FactRow`, e adicionar:

```python
@router.get("/facts", response_model=list[FactRow])
async def facts(
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
    from_: date = Query(..., alias="from"), to: date = Query(...),
):
    return [FactRow(**row) for row in await compute_facts(session, from_, to)]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/api/schemas/accounting.py backend/api/routes/accounting.py backend/tests/api/test_accounting.py
git commit -m "feat(contabil): endpoint GET /accounting/facts"
```

---

## Task 3: `itens_label` no `SaleOut` (aba Vendas)

**Files:**
- Modify: `backend/api/schemas/accounting.py`, `backend/api/routes/accounting.py`
- Test: `backend/tests/api/test_accounting.py`

- [ ] **Step 1: Teste**

Acrescentar a `backend/tests/api/test_accounting.py` (seguir o helper `_seed_commercial_quote` já existente no arquivo, que cria um orçamento comercial aprovado; depois conferir que a venda materializada traz `itens_label`):

```python
@pytest.mark.asyncio
async def test_sales_have_itens_label(auth_client):
    import sqlalchemy as sa
    from decimal import Decimal
    from backend.core.models import QuoteKind, QuoteStatus
    from backend.infra.db import session as session_module
    from backend.infra.db.models import MaterialVersion, Quote, QuoteItem, User
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        mv = MaterialVersion(material_type="PLA", name="PLA", color="Azul",
                             density_g_cm3=Decimal("1.24"), price_per_kg_ref=Decimal("100"))
        s.add(mv); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.APROVADO.value, markup_pct=Decimal("0"), min_charge=Decimal("0"))
        s.add(q); await s.commit()
        s.add(QuoteItem(quote_id=q.id, name="Vaso", gcode_meta={"filament_g": 10},
                        material_version_id=mv.id, quantity=2))
        await s.commit()

    r = await auth_client.get("/accounting/sales")
    assert r.status_code == 200, r.text
    sale = next(x for x in r.json() if x["quote_id"] == str(q.id))
    assert sale["itens_label"] == "Vaso ×2 (Azul)"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py::test_sales_have_itens_label -q`
Expected: FAIL — `itens_label` ausente.

- [ ] **Step 3: Implementar**

Em `backend/api/schemas/accounting.py`, em `SaleOut`, adicionar:
```python
    itens_label: str = ""
```

Em `backend/api/routes/accounting.py`:
- importar: `from backend.core.accounting.facts import sale_items_label`
- mudar `_sale_out` para aceitar o rótulo e incluí-lo:
```python
def _sale_out(s: Sale, itens_label: str = "") -> SaleOut:
    return SaleOut(
        id=str(s.id), quote_id=str(s.quote_id), quote_status=s.quote_status,
        quote_total=s.quote_total, cpv_calc=s.cpv_calc,
        client_id=str(s.client_id) if s.client_id else None,
        is_stale=s.is_stale, is_sold=s.is_sold, confirmed_revenue=s.confirmed_revenue,
        variable_costs=s.variable_costs, cpv_override=s.cpv_override,
        sold_at=s.sold_at, notes=s.notes, itens_label=itens_label,
    )
```
- em `list_sales`, montar o rótulo por venda:
```python
    rows = (await session.execute(stmt)).scalars().all()
    return [_sale_out(s, await sale_items_label(session, s)) for s in rows]
```
- nos outros call sites de `_sale_out` (no `update_sale`), manter sem rótulo (passa só `sale`); o default `""` cobre. *(opcional: também montar lá; não é necessário pro fix.)*

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/api/schemas/accounting.py backend/api/routes/accounting.py backend/tests/api/test_accounting.py
git commit -m "feat(contabil): itens_label (nomes pipe) no SaleOut"
```

---

## Task 4: Aba `Fato (itens)` no XLSX

**Files:**
- Modify: `backend/core/accounting/export_xlsx.py`
- Test: `backend/tests/api/test_accounting.py`

- [ ] **Step 1: Teste**

Atualizar `test_dre_export_xlsx` (ou adicionar um caso) em `backend/tests/api/test_accounting.py` para conferir a aba nova:

```python
@pytest.mark.asyncio
async def test_xlsx_has_facts_sheet(auth_client):
    import io
    from openpyxl import load_workbook
    r = await auth_client.get("/accounting/dre/export.xlsx?from=2026-06-01&to=2026-06-30")
    assert r.status_code == 200, r.text
    wb = load_workbook(io.BytesIO(r.content))
    assert "Fato (itens)" in wb.sheetnames
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py::test_xlsx_has_facts_sheet -q`
Expected: FAIL — aba ausente.

- [ ] **Step 3: Implementar**

Em `backend/core/accounting/export_xlsx.py`, importar `compute_facts` (`from backend.core.accounting.facts import compute_facts`) e, **antes** de `buf = io.BytesIO()`, adicionar a aba:

```python
    ws = wb.create_sheet("Fato (itens)")
    cols = ["sale_id", "quote_id", "quote_kind", "cliente", "status", "sold_at", "is_sold",
            "receita_venda", "custos_variaveis_venda", "cpv_venda", "item_id", "nome",
            "quantidade", "material_type", "cor_material", "cor_bobina", "filament_m",
            "filament_g", "gramas_total", "custo_filamento_item", "receita_item"]
    ws.append(cols)
    for row in await compute_facts(session, period_from, period_to):
        ws.append([
            row["sale_id"], row["quote_id"], row["quote_kind"], row["cliente"], row["status"],
            row["sold_at"].isoformat() if row["sold_at"] else "", row["is_sold"],
            float(row["receita_venda"]), float(row["custos_variaveis_venda"]), float(row["cpv_venda"]),
            row["item_id"], row["nome"], row["quantidade"], row["material_type"],
            row["cor_material"] or "", row["cor_bobina"] or "",
            row["filament_m"] if row["filament_m"] is not None else "",
            row["filament_g"] if row["filament_g"] is not None else "",
            float(row["gramas_total"]), float(row["custo_filamento_item"]), float(row["receita_item"]),
        ])
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_accounting.py -q`
Expected: PASS (todos).

- [ ] **Step 5: Commit**

```bash
git add backend/core/accounting/export_xlsx.py backend/tests/api/test_accounting.py
git commit -m "feat(contabil): aba Fato (itens) no export XLSX"
```

---

## Task 5: Frontend — coluna Itens na aba Vendas

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/routes/accounting/+page.svelte`

- [ ] **Step 1: Tipo**

Em `frontend/src/lib/types.ts`, em `Sale`, adicionar `itens_label: string;`.

- [ ] **Step 2: Coluna**

Na tabela de Vendas (`frontend/src/routes/accounting/+page.svelte`), adicionar uma coluna "Itens" que mostra `itens_label`. Usar o componente `Table` com uma coluna `{ key: "itens_label", label: "Itens" }` (texto puro; o backend já formata `Vaso ×2 (Azul) | Suporte ×1 (Verde)`). Posicionar antes ou depois de "Tipo", seguindo o estilo das demais colunas.

- [ ] **Step 3: Check**

Run: `cd frontend && npm run check`
Expected: sem erros novos (só os pré-existentes de library/spools).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/routes/accounting/+page.svelte
git commit -m "feat(contabil): coluna Itens (pipe) na aba Vendas"
```

---

## Task 6: Verificação

- [ ] **Step 1:** `docker compose run --rm api pytest backend/tests -q` → tudo PASS.
- [ ] **Step 2:** `cd frontend && npm run check` → sem erros novos.
- [ ] **Step 3:** `docker compose run --rm api ruff check backend/core/accounting/facts.py backend/api/routes/accounting.py backend/core/accounting/export_xlsx.py` → sem erros novos (E702 de estilo é tolerado).

---

## Notas

- **Granularidade:** o fato repete medidas de venda em cada item — pra somar receita/CPV, dedup por `sale_id`; medidas de item somam direto. (Spec §2.3.)
- **`effective_grams_per_unit` com `waste_pct=0`** mantém paridade com o custo-orçado da Contábil (que também usa 0).
- **Cor da bobina** vem de `MaterialConsumption → Spool.color`; nula para itens não produzidos (cai na `cor_material` no rótulo da aba Vendas).
- **Performance:** `list_sales` agora monta o rótulo por venda (queries por item). Aceitável na escala atual; se a tabela crescer muito, dá pra mover o rótulo pro `compute_facts` agregado.
