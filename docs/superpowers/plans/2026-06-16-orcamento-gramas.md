# Orçamento — gramas gastas como base de custo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir informar `filament_g` (gramas por peça, valor final) num item do orçamento; quando presente, o custo usa as gramas direto em vez de derivar dos metros.

**Architecture:** Um helper único `effective_grams_per_unit` centraliza a decisão (override de gramas vs. derivação por metros + refugo). Os três pontos que hoje derivam gramas passam a chamá-lo: o custo do orçamento (`gcode_to_item_input`), a estimativa de baixa na produção (`grams_for_item`) e o custo-orçado da Contábil (`compute_quote_costs`). API e UI ganham o campo de gramas.

**Tech Stack:** FastAPI + SQLAlchemy async, pytest (rodar via `docker compose run --rm api pytest …`), SvelteKit + TS (`cd frontend && npm run check`).

**Spec:** `docs/superpowers/specs/2026-06-16-orcamento-gramas-design.md`

---

## File Structure

- `backend/core/quote_service.py` — novo `effective_grams_per_unit`; `gcode_to_item_input` e `grams_for_item` passam a usá-lo.
- `backend/core/accounting/cost.py` — `compute_quote_costs` usa o helper (waste_pct=0, preserva v1).
- `backend/api/schemas/quotes.py` — `QuoteItemUpdate.filament_g`.
- `backend/api/routes/quotes.py` — `update_item` grava/limpa `gcode_meta["filament_g"]`.
- `frontend/src/routes/quotes/[id]/+page.svelte` — editor de gramas no item.
- Testes: `backend/tests/core/test_quote_service.py` (ou novo arquivo), `backend/tests/core/test_accounting_cost.py`, `backend/tests/api/test_quotes_lifecycle.py`.

---

## Task 1: Helper `effective_grams_per_unit`

**Files:**
- Modify: `backend/core/quote_service.py`
- Test: `backend/tests/core/test_quote_service_grams.py` (novo)

- [ ] **Step 1: Escrever o teste**

`backend/tests/core/test_quote_service_grams.py`:

```python
from decimal import Decimal

from backend.core.quote_service import effective_grams_per_unit

_D = Decimal("1.75")


def test_override_wins_no_waste():
    # filament_g preenchido -> usa direto, ignora metros e refugo
    g = effective_grams_per_unit(filament_m=10.0, filament_g=25.0,
                                 density=Decimal("1.24"), diameter_mm=_D,
                                 waste_pct=Decimal("20"))
    assert g == Decimal("25")


def test_no_override_derives_with_waste():
    base = effective_grams_per_unit(filament_m=10.0, filament_g=None,
                                    density=Decimal("1.24"), diameter_mm=_D,
                                    waste_pct=Decimal("0"))
    withw = effective_grams_per_unit(filament_m=10.0, filament_g=None,
                                     density=Decimal("1.24"), diameter_mm=_D,
                                     waste_pct=Decimal("10"))
    assert base > 0
    assert withw == base * Decimal("110") / Decimal("100")


def test_zero_grams_falls_back_to_meters():
    g0 = effective_grams_per_unit(filament_m=10.0, filament_g=0.0,
                                  density=Decimal("1.24"), diameter_mm=_D,
                                  waste_pct=Decimal("0"))
    gm = effective_grams_per_unit(filament_m=10.0, filament_g=None,
                                  density=Decimal("1.24"), diameter_mm=_D,
                                  waste_pct=Decimal("0"))
    assert g0 == gm
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_quote_service_grams.py -q`
Expected: FAIL — `ImportError: cannot import name 'effective_grams_per_unit'`.

- [ ] **Step 3: Implementar**

Em `backend/core/quote_service.py`, adicionar (o módulo já importa `grams_from_meters`):

```python
def effective_grams_per_unit(
    filament_m: float,
    filament_g: float | None,
    density: Decimal,
    diameter_mm: Decimal,
    waste_pct: Decimal,
) -> Decimal:
    """Gramas por peça para custo.

    Se ``filament_g`` está preenchido e > 0, é o valor final (sem refugo).
    Senão, deriva dos metros e aplica ``waste_pct``.
    """
    if filament_g is not None and filament_g > 0:
        return Decimal(str(filament_g))
    grams = grams_from_meters(filament_m, density, diameter_mm)
    if waste_pct > 0:
        grams = grams * (Decimal(100) + waste_pct) / Decimal(100)
    return grams
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_quote_service_grams.py -q`
Expected: PASS (3 testes).

- [ ] **Step 5: Commit**

```bash
git add backend/core/quote_service.py backend/tests/core/test_quote_service_grams.py
git commit -m "feat(orcamento): helper effective_grams_per_unit"
```

---

## Task 2: Caminho do custo do orçamento + estimativa de produção usam o helper

**Files:**
- Modify: `backend/core/quote_service.py` (`gcode_to_item_input`, `grams_for_item`)
- Modify: `backend/api/routes/quotes.py` (`_build_item_input` passa `filament_g`)
- Test: `backend/tests/core/test_quote_service_grams.py`

- [ ] **Step 1: Escrever o teste (custo do item honra override)**

Acrescentar a `backend/tests/core/test_quote_service_grams.py`:

```python
from backend.core.quote_service import gcode_to_item_input
from backend.core.gcode.parser import GcodeMeta
from backend.core.pricing.quote import compute_item_cost


def test_item_input_uses_grams_override():
    meta = GcodeMeta(time_s=0.0, filament_m=10.0, material=None, machine=None)
    ii = gcode_to_item_input(
        meta=meta, density=Decimal("1.24"), price_per_kg=Decimal("100"),
        power_w=Decimal("0"), kwh_price=Decimal("0"), depreciation_per_hour=Decimal("0"),
        failure_pct=Decimal("0"), quantity=1, waste_pct=Decimal("20"),
        filament_g=50.0,
    )
    # 50 g a R$100/kg = R$5,00 (sem refugo aplicado por cima)
    assert compute_item_cost(ii) == Decimal("5.00")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_quote_service_grams.py::test_item_input_uses_grams_override -q`
Expected: FAIL — `gcode_to_item_input() got an unexpected keyword argument 'filament_g'`.

- [ ] **Step 3: Implementar nos dois pontos do quote_service**

Em `backend/core/quote_service.py`, `gcode_to_item_input`: adicionar o parâmetro `filament_g: float | None = None` e trocar o cálculo de `grams`:

```python
def gcode_to_item_input(
    meta: GcodeMeta,
    density: Decimal,
    price_per_kg: Decimal,
    power_w: Decimal,
    kwh_price: Decimal,
    depreciation_per_hour: Decimal,
    failure_pct: Decimal,
    quantity: int,
    diameter_mm: Decimal = Decimal("1.75"),
    maintenance_per_hour: Decimal = Decimal("0"),
    waste_pct: Decimal = Decimal("0"),
    filament_g: float | None = None,
) -> ItemInput:
    grams = effective_grams_per_unit(meta.filament_m, filament_g, density, diameter_mm, waste_pct)
    return ItemInput(
        grams=grams,
        price_per_kg=price_per_kg,
        time_s=meta.time_s,
        power_w=power_w,
        kwh_price=kwh_price,
        depreciation_per_hour=depreciation_per_hour,
        failure_pct=failure_pct,
        quantity=quantity,
        maintenance_per_hour=maintenance_per_hour,
    )
```

(Remover o antigo bloco `grams = grams_from_meters(...)` + `if waste_pct > 0:` — agora vive no helper.)

E `grams_for_item` passa a honrar o override também (estimativa de baixa na produção; sem refugo, como hoje):

```python
def grams_for_item(meta_dict: dict, density: Decimal, quantity: int,
                   diameter_mm: Decimal = Decimal("1.75")) -> Decimal:
    """Total de gramas consumidas por um item com `quantity` cópias."""
    meters = float(meta_dict.get("filament_m") or 0)
    raw_g = meta_dict.get("filament_g")
    filament_g = float(raw_g) if raw_g not in (None, "") else None
    per_unit = effective_grams_per_unit(meters, filament_g, density, diameter_mm, Decimal("0"))
    return per_unit * Decimal(quantity)
```

- [ ] **Step 4: Passar `filament_g` no `_build_item_input`**

Em `backend/api/routes/quotes.py`, dentro de `_build_item_input`, na chamada a `gcode_to_item_input(...)`, acrescentar o argumento:

```python
        filament_g=(float(it.gcode_meta["filament_g"])
                    if it.gcode_meta.get("filament_g") not in (None, "") else None),
```

- [ ] **Step 5: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_quote_service_grams.py -q`
Expected: PASS (4 testes).

Garantir que não quebrou o lifecycle existente:
Run: `docker compose run --rm api pytest backend/tests/api/test_quotes_lifecycle.py backend/tests/core/test_pricing_quote.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/core/quote_service.py backend/api/routes/quotes.py backend/tests/core/test_quote_service_grams.py
git commit -m "feat(orcamento): custo e estimativa de produção honram filament_g"
```

---

## Task 3: Contábil (`compute_quote_costs`) honra o override

**Files:**
- Modify: `backend/core/accounting/cost.py`
- Test: `backend/tests/core/test_accounting_cost.py`

- [ ] **Step 1: Escrever o teste**

Acrescentar a `backend/tests/core/test_accounting_cost.py`:

```python
@pytest.mark.asyncio
async def test_compute_quote_costs_honors_filament_g():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="grams@t.com", password_hash="x")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"))
        settings = await s.merge(Settings(id=1, energy_kwh_price=Decimal("0"),
                                          printer_power_w=Decimal("0"),
                                          printer_depreciation_per_hour=Decimal("0")))
        s.add_all([user, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        item = QuoteItem(quote_id=q.id, name="p",
                         gcode_meta={"filament_m": 10, "time_s": 0, "filament_g": 50},
                         material_version_id=mv.id, quantity=1)
        s.add(item); await s.commit()

        costs = await compute_quote_costs(s, q, settings)
        # 50 g a R$100/kg = R$5,00 (override; sem refugo)
        assert costs.catalog_filament == Decimal("5.00")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_cost.py::test_compute_quote_costs_honors_filament_g -q`
Expected: FAIL — catalog_filament deriva dos metros (≈ valor diferente de 5.00).

- [ ] **Step 3: Implementar**

Em `backend/core/accounting/cost.py`, importar o helper no topo:

```python
from backend.core.quote_service import effective_grams_per_unit
```

Dentro de `compute_quote_costs`, no loop por item, substituir o cálculo de `catalog_filament` por unidade:

```python
        filament_m = float(it.gcode_meta.get("filament_m", 0) or 0)
        raw_g = it.gcode_meta.get("filament_g")
        filament_g = float(raw_g) if raw_g not in (None, "") else None
        grams_unit = effective_grams_per_unit(
            filament_m, filament_g, mv.density_g_cm3, _DIAMETER_MM, Decimal("0")
        )
        grams = grams_unit * Decimal(it.quantity)
        catalog_filament += filament_cost(grams, mv.price_per_kg_ref)
```

(Remover as linhas antigas que calculavam `area`/`grams_per_m`/`grams` via `_PI`. Manter `time_s`, energia, depreciação e o consumo real (`real_filament`) como estão. `_PI` pode ficar se ainda usado; se não, remover.)

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_accounting_cost.py -q`
Expected: PASS (todos, incluindo o novo).

- [ ] **Step 5: Commit**

```bash
git add backend/core/accounting/cost.py backend/tests/core/test_accounting_cost.py
git commit -m "feat(contabil): compute_quote_costs honra filament_g"
```

---

## Task 4: API — campo `filament_g` no update do item

**Files:**
- Modify: `backend/api/schemas/quotes.py`
- Modify: `backend/api/routes/quotes.py` (`update_item`)
- Test: `backend/tests/api/test_quotes_lifecycle.py`

- [ ] **Step 1: Escrever o teste**

Acrescentar a `backend/tests/api/test_quotes_lifecycle.py` (seguir o estilo de criação de quote/item já usado no arquivo; este teste cria um item, seta `filament_g`, confere que `gcode_meta` reflete, e que enviar `0` limpa):

```python
@pytest.mark.asyncio
async def test_item_filament_g_set_and_clear(auth_client):
    # cria quote comercial
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    # adiciona item manual (sem gcode)
    r = await auth_client.post(f"/quotes/{qid}/items", data={"name": "peça"})
    assert r.status_code == 201, r.text
    item_id = r.json()["items"][0]["id"]

    # seta gramas
    r = await auth_client.put(f"/quotes/{qid}/items/{item_id}", json={"filament_g": 42})
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["id"] == item_id)
    assert float(item["gcode_meta"].get("filament_g")) == 42.0

    # zera -> limpa a chave
    r = await auth_client.put(f"/quotes/{qid}/items/{item_id}", json={"filament_g": 0})
    item = next(i for i in r.json()["items"] if i["id"] == item_id)
    assert "filament_g" not in item["gcode_meta"]
```

NOTA: confirmar a forma de criar item manual no arquivo de teste (o endpoint `POST /quotes/{id}/items` aceita multipart com `name`). Se o helper de criação difere, seguir o padrão já presente no arquivo.

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_quotes_lifecycle.py::test_item_filament_g_set_and_clear -q`
Expected: FAIL — `filament_g` é ignorado (não aparece/não limpa).

- [ ] **Step 3: Schema**

Em `backend/api/schemas/quotes.py`, na classe `QuoteItemUpdate`, adicionar (junto de `filament_m`):

```python
    filament_g: float | None = None
```

- [ ] **Step 4: Handler**

Em `backend/api/routes/quotes.py`, dentro de `update_item`, logo após o bloco que trata `payload.filament_m`, acrescentar:

```python
    if payload.filament_g is not None:
        if payload.filament_g < 0:
            raise HTTPException(400, "filament_g must be >= 0")
        meta = dict(it.gcode_meta or {})
        if payload.filament_g > 0:
            meta["filament_g"] = float(payload.filament_g)
        else:
            meta.pop("filament_g", None)
        it.gcode_meta = meta
```

- [ ] **Step 5: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_quotes_lifecycle.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/api/schemas/quotes.py backend/api/routes/quotes.py backend/tests/api/test_quotes_lifecycle.py
git commit -m "feat(orcamento): API aceita filament_g no item (0 limpa)"
```

---

## Task 5: Frontend — editor de gramas no item

**Files:**
- Modify: `frontend/src/routes/quotes/[id]/+page.svelte`

- [ ] **Step 1: Localizar o editor de metros**

O item tem um editor inline de `filament_m` (~linha 731, input com `value={Number(it.gcode_meta?.filament_m ?? 0).toFixed(2)}` e um `patchItem(itemId, { filament_m: meters }, "filament")` por volta da linha 399). Estudar esse trecho para replicar o padrão de input/patch.

- [ ] **Step 2: Adicionar a função de patch de gramas**

Perto de onde `filament_m` é persistido (a função que chama `patchItem(itemId, { filament_m: ... })`), adicionar uma análoga para gramas, ex.:

```js
  function saveGrams(itemId, value) {
    const g = value === "" ? 0 : Number(value);
    if (!Number.isFinite(g) || g < 0) return;
    patchItem(itemId, { filament_g: g }, "filament");
  }
```

(`filament_g: 0` limpa o override no backend.)

- [ ] **Step 3: Adicionar o campo na célula de Filamento**

Na coluna "Filamento" do item, abaixo/ao lado do input de metros, adicionar um input de gramas com dica de que sobrescreve:

```svelte
<input
  class="mini"
  type="number"
  step="0.1"
  min="0"
  placeholder="g (gastas)"
  title="Se preenchido, ignora os metros pro custo"
  value={it.gcode_meta?.filament_g ?? ""}
  on:change={(e) => saveGrams(it.id, e.currentTarget.value)}
/>
```

Quando `it.gcode_meta?.filament_g` estiver preenchido, indicar visualmente que o custo está vindo das gramas (ex.: um rótulo "por peso" ao lado), seguindo o estilo das outras dicas da tela.

- [ ] **Step 4: Type-check**

Run: `cd frontend && npm run check`
Expected: sem erros novos. (`gcode_meta` já é `dict`/`Record<string, unknown>` no tipo do item; usar `Number(...)`/casts como o resto da tela faz.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/quotes/[id]/+page.svelte
git commit -m "feat(orcamento): campo de gramas (gastas) no editor do item"
```

---

## Task 6: Verificação

- [ ] **Step 1: Suíte backend verde**

Run: `docker compose run --rm api pytest backend/tests -q`
Expected: tudo PASS.

- [ ] **Step 2: Frontend check**

Run: `cd frontend && npm run check`
Expected: sem erros novos (mesmos pré-existentes de library/spools, se houver).

- [ ] **Step 3: Ruff**

Run: `docker compose run --rm api ruff check backend/core/quote_service.py backend/core/accounting/cost.py backend/api/routes/quotes.py`
Expected: sem erros novos (o estilo de ponto-e-vírgula pré-existente do repo é tolerado).

---

## Notas

- **PDF:** `backend/infra/pdf/render.py` não exibe gramas/metros de filamento hoje, então não há mudança de PDF nesta rodada (a spec dizia "onde aparece" — não aparece).
- **Refugo:** o `waste_pct` continua aplicado só na derivação por metros. No caminho da Contábil (`compute_quote_costs`) passamos `waste_pct=0`, preservando os números da v1; quando há `filament_g`, ambos os caminhos retornam o mesmo valor e batem.
