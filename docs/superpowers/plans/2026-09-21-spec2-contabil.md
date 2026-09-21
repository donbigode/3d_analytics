# Spec 2 — Contábil: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tirar o uso pessoal da lista de venda, tornar a data de venda uma escolha explícita, dar busca às listas do Contábil e eliminar o GET que escreve.

**Architecture:** `GET /accounting/sales` ganha filtro por tipo e para de chamar `sync_sales()`; o pessoal ganha sub-aba própria que mostra perda operacional; o checkbox "Vendido" vira um fluxo de registro com data; a listagem passa a resolver rótulos e nomes em lote.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, pytest, SvelteKit 2 + Svelte 5, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-21-contabil-vendas-pessoais-design.md`

## Global Constraints

- **Depende das Specs 0 e 1 concluídas** — `$lib/resource`, `$lib/format`, `SearchBar`, `Table` com busca, e `SaleOut.quote_seq`.
- **A regra de DRE não muda:** uso pessoal produzido e não vendido continua sendo perda operacional pelo CPV cheio.
- `sold_at` já existe no modelo e no `SaleUpdate`. **Nenhuma migração de schema** — só a de dados (Task 1).
- Busca e filtros são client-side. `kind` é a única exceção: é parâmetro de API, porque separa as abas.
- Tudo roda via Docker Compose: `make test`, `make lint`, `make e2e`.
- Mensagens de commit terminam com `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## ⚠️ Dois testes existentes mudam nesta spec

Diferente da Spec 0, aqui o comportamento **muda de propósito**. Dois testes em
`backend/tests/api/test_accounting.py` afirmam exatamente o que vai embora:

1. **`test_confirming_sale_backfills_revenue_and_date`** (linha 39) afirma que
   confirmar sem data preenche `sold_at` com hoje. A Spec 2 §4.1 substitui isso
   por 422. O teste é **reescrito** na Task 3 para afirmar o comportamento novo,
   preservando a metade que continua valendo (`confirmed_revenue` ainda recebe
   default de `quote_total`).
2. **`test_sales_listed_after_sync_and_patch`** (linha 21) tem o comentário
   *"GET dispara o sync e materializa a venda"*. A Task 5 tira o sync do GET; o
   teste passa a chamar `POST /accounting/sync` antes do GET.

Nenhum outro teste é alterado. Se um terceiro teste quebrar, é regressão.

---

### Task 1: Backfill de `sales.quote_kind`

**Files:**
- Create: `migrations/versions/0033_sales_quote_kind_backfill.py`
- Test: `backend/tests/api/test_sales_kind_filter.py`

**Interfaces:**
- Consumes: nada.
- Produces: garantia de que `sales.quote_kind` reflete `quotes.kind` em toda linha.

- [ ] **Step 1: Escrever o teste que falha**

Create `backend/tests/api/test_sales_kind_filter.py`:

```python
"""Separação de comercial e pessoal no contábil.

O backfill corrige linhas arquivadas (is_stale) criadas antes da coluna
quote_kind existir: elas nasceram com o server_default 'commercial' e
nunca são re-sincronizadas, porque sync_sales ignora quem saiu dos
status ativos.
"""
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, Sale, User


async def _quote(kind: QuoteKind, status: QuoteStatus) -> Quote:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=kind.value, user_id=u.id, status=status.value,
                  markup_pct=Decimal("100"), min_charge=Decimal("0"))
        s.add(q)
        await s.commit()
        await s.refresh(q)
        return q


@pytest.mark.asyncio
async def test_backfill_corrige_linha_arquivada_com_kind_errado(auth_client):
    q = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    await auth_client.post("/accounting/sync")

    # Simula o estado legado: linha arquivada marcada como comercial.
    async with session_module.SessionFactory() as s:
        sale = (await s.execute(sa.select(Sale).where(Sale.quote_id == q.id))).scalars().one()
        sale.quote_kind = QuoteKind.COMMERCIAL.value
        sale.is_stale = True
        await s.commit()

    # Aplicar o mesmo UPDATE da migração.
    async with session_module.SessionFactory() as s:
        await s.execute(sa.text(
            "UPDATE sales s SET quote_kind = q.kind FROM quotes q "
            "WHERE q.id = s.quote_id AND s.quote_kind IS DISTINCT FROM q.kind"
        ))
        await s.commit()
        corrigida = (await s.execute(sa.select(Sale).where(Sale.quote_id == q.id))).scalars().one()
        assert corrigida.quote_kind == QuoteKind.PERSONAL.value


@pytest.mark.asyncio
async def test_backfill_e_idempotente(auth_client):
    await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    await auth_client.post("/accounting/sync")
    sql = sa.text(
        "UPDATE sales s SET quote_kind = q.kind FROM quotes q "
        "WHERE q.id = s.quote_id AND s.quote_kind IS DISTINCT FROM q.kind"
    )
    async with session_module.SessionFactory() as s:
        r1 = await s.execute(sql)
        await s.commit()
        r2 = await s.execute(sql)
        await s.commit()
        assert r2.rowcount == 0, "segunda execução deveria não tocar em nada"
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/api/test_sales_kind_filter.py -v
```

Expected: FAIL — `POST /accounting/sync` existe, então pode passar já; se passar, seguir mesmo assim (o teste documenta a semântica que a migração aplica).

- [ ] **Step 3: Escrever a migração de dados**

Create `migrations/versions/0033_sales_quote_kind_backfill.py`:

```python
"""Backfill de sales.quote_kind

quote_kind nasceu com server_default 'commercial' e só é reescrito por
sync_sales(), que ignora orçamentos fora dos status ativos. Logo, linhas
arquivadas (is_stale) de orçamentos PESSOAIS criadas antes da coluna
ficaram marcadas como comerciais — e apareceriam na aba errada.

Só dados, sem schema. Idempotente. downgrade é no-op: não há como saber
quais linhas foram tocadas, e restaurar um valor sabidamente errado não
serve a ninguém.

Revision ID: 0033_sales_quote_kind_backfill
Revises: 0032_quote_seq
Create Date: 2026-09-21 11:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0033_sales_quote_kind_backfill"
down_revision: Union[str, Sequence[str], None] = "0032_quote_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE sales s
           SET quote_kind = q.kind
          FROM quotes q
         WHERE q.id = s.quote_id
           AND s.quote_kind IS DISTINCT FROM q.kind
        """
    )


def downgrade() -> None:
    """No-op — ver docstring do módulo."""
```

- [ ] **Step 4: Rodar tudo**

```bash
docker compose run --rm api alembic upgrade head
docker compose run --rm api pytest backend/tests/api/test_sales_kind_filter.py -v
make test 2>&1 | tail -5
```

Expected: verde.

- [ ] **Step 5: Conferir o efeito no banco de dev**

```bash
docker compose run --rm api python -c "
import asyncio, sqlalchemy as sa
from backend.infra.db.session import SessionFactory
async def main():
    async with SessionFactory() as s:
        r = (await s.execute(sa.text(
            'SELECT count(*) FROM sales s JOIN quotes q ON q.id = s.quote_id '
            'WHERE s.quote_kind IS DISTINCT FROM q.kind'))).scalar()
        print('linhas divergentes após o backfill:', r)
        assert r == 0
asyncio.run(main())
"
```

Expected: `linhas divergentes após o backfill: 0`.

- [ ] **Step 6: Commit**

```bash
git add migrations/versions/0033_sales_quote_kind_backfill.py \
        backend/tests/api/test_sales_kind_filter.py
git commit -m "fix(contábil): backfill de sales.quote_kind

Corrige pessoais arquivados marcados como comerciais — linhas que
sync_sales nunca re-sincroniza. Idempotente.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Filtro por tipo e `produced_on` na listagem

**Files:**
- Modify: `backend/api/routes/accounting.py`
- Modify: `backend/api/schemas/accounting.py`
- Test: `backend/tests/api/test_sales_kind_filter.py` (estende)

**Interfaces:**
- Consumes: `Sale.quote_kind`.
- Produces: `GET /accounting/sales?kind=commercial|personal`; `SaleOut.quote_kind: str` e `SaleOut.produced_on: date | None`.

`produced_on` é o menor `consumed_at` das baixas do orçamento — o mesmo critério de atribuição de período que `_perda_operacional` usa em `backend/core/accounting/dre.py`. É o que permite o rodapé da aba pessoal bater com o DRE.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar a `backend/tests/api/test_sales_kind_filter.py`:

```python
@pytest.mark.asyncio
async def test_filtro_kind_separa_as_listas(auth_client):
    com = await _quote(QuoteKind.COMMERCIAL, QuoteStatus.APROVADO)
    pes = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    await auth_client.post("/accounting/sync")

    r = await auth_client.get("/accounting/sales?kind=commercial")
    ids = {v["quote_id"] for v in r.json()}
    assert str(com.id) in ids
    assert str(pes.id) not in ids

    r = await auth_client.get("/accounting/sales?kind=personal")
    ids = {v["quote_id"] for v in r.json()}
    assert str(pes.id) in ids
    assert str(com.id) not in ids


@pytest.mark.asyncio
async def test_sem_kind_devolve_ambos(auth_client):
    com = await _quote(QuoteKind.COMMERCIAL, QuoteStatus.APROVADO)
    pes = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    await auth_client.post("/accounting/sync")
    ids = {v["quote_id"] for v in (await auth_client.get("/accounting/sales")).json()}
    assert {str(com.id), str(pes.id)} <= ids


@pytest.mark.asyncio
async def test_sale_out_traz_quote_kind_e_produced_on(auth_client):
    pes = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    await auth_client.post("/accounting/sync")
    venda = next(v for v in (await auth_client.get("/accounting/sales")).json()
                 if v["quote_id"] == str(pes.id))
    assert venda["quote_kind"] == "personal"
    # Sem baixa de material, produced_on é nulo — o DRE cai no created_at.
    assert "produced_on" in venda
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/api/test_sales_kind_filter.py -v
```

Expected: FAIL — parâmetro `kind` não existe; `quote_kind` e `produced_on` não estão no `SaleOut`.

- [ ] **Step 3: Estender o schema e a assinatura de `_sale_out`**

Em `backend/api/schemas/accounting.py`, na classe `SaleOut`:

```python
    quote_kind: str
    produced_on: date | None = None
```

E em `backend/api/routes/accounting.py`, `_sale_out` ganha os dois campos novos
(`quote_seq` veio da Spec 1, Task 2). A assinatura final, que a Task 4 usa por
keyword, é:

```python
def _sale_out(s: Sale, itens_label: str = "", client_name: str | None = None,
              quote_seq: int = 0, produced_on: date | None = None) -> SaleOut:
    return SaleOut(
        id=str(s.id), quote_id=str(s.quote_id), quote_seq=quote_seq,
        quote_kind=s.quote_kind, produced_on=produced_on,
        # ...demais campos exatamente como já estão no arquivo, sem alteração
    )
```

- [ ] **Step 4: Implementar o filtro e o cálculo em lote**

Em `backend/api/routes/accounting.py`:

```python
from backend.core.models import QuoteKind
from backend.infra.db.models import MaterialConsumption, Quote, QuoteItem


@router.get("/sales", response_model=list[SaleOut])
async def list_sales(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
    kind: QuoteKind | None = Query(None),
    is_sold: bool | None = Query(None),
    is_stale: bool | None = Query(None),
):
    stmt = select(Sale).order_by(Sale.created_at.desc())
    if kind is not None:
        stmt = stmt.where(Sale.quote_kind == kind.value)
    if is_sold is not None:
        stmt = stmt.where(Sale.is_sold.is_(is_sold))
    if is_stale is not None:
        stmt = stmt.where(Sale.is_stale.is_(is_stale))
    rows = (await session.execute(stmt)).scalars().all()
    # ...montagem das linhas segue abaixo, reescrita em lote na Task 4
```

Repare que o `await sync_sales(session)` **saiu** — é a Task 5 que trata disso, mas como ela mexe no mesmo endpoint, fazer as duas juntas evita reescrever. Se preferir separar, manter o sync aqui e removê-lo na Task 5.

O cálculo de `produced_on`, em lote:

```python
async def _produced_on_map(session: AsyncSession, quote_ids: list[UUID]) -> dict[UUID, date]:
    """Menor consumed_at por orçamento — mesmo critério de atribuição de
    período que _perda_operacional usa no DRE. Uma query para todos."""
    if not quote_ids:
        return {}
    rows = (
        await session.execute(
            select(QuoteItem.quote_id, func.min(MaterialConsumption.consumed_at))
            .join(MaterialConsumption, MaterialConsumption.quote_item_id == QuoteItem.id)
            .where(QuoteItem.quote_id.in_(quote_ids))
            .group_by(QuoteItem.quote_id)
        )
    ).all()
    return {qid: (dt.date() if hasattr(dt, "date") else dt) for qid, dt in rows}
```

Importar `func` de `sqlalchemy` e `date` de `datetime` (já importado).

- [ ] **Step 5: Rodar e confirmar que passa**

```bash
docker compose run --rm api pytest backend/tests/api/test_sales_kind_filter.py -v
make test 2>&1 | tail -5
make lint
```

- [ ] **Step 6: Atualizar os tipos do frontend**

Em `frontend/src/lib/types.ts`, adicionar `quote_kind: string` e `produced_on: string | null` a `Sale`.

- [ ] **Step 7: Commit**

```bash
git add backend/api/ backend/tests/api/test_sales_kind_filter.py frontend/src/lib/types.ts
git commit -m "feat(contábil): filtro ?kind= e produced_on na listagem de vendas

produced_on usa o mesmo critério do DRE (menor consumed_at), em lote.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Data de venda explícita

**Files:**
- Modify: `backend/api/routes/accounting.py` (`update_sale`)
- Modify: `backend/tests/api/test_accounting.py` (**reescreve** `test_confirming_sale_backfills_revenue_and_date`)
- Test: `backend/tests/api/test_sale_date.py`

**Interfaces:**
- Consumes: `Sale.sold_at` (já existe).
- Produces: `PATCH /accounting/sales/{id}` com 422 quando falta data; resposta completa com `itens_label`, `client_name`, `quote_seq`.

- [ ] **Step 1: Escrever os testes do comportamento novo**

Create `backend/tests/api/test_sale_date.py`:

```python
"""Data de venda é escolha explícita, não efeito colateral do clique.

Antes: marcar is_sold gravava date.today() escondido, e o item caía no
mês corrente do DRE mesmo tendo sido vendido em outro.
"""
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, User


async def _venda(auth_client) -> dict:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.APROVADO.value, markup_pct=Decimal("100"),
                  min_charge=Decimal("0"))
        s.add(q)
        await s.commit()
    await auth_client.post("/accounting/sync")
    return (await auth_client.get("/accounting/sales?kind=commercial")).json()[0]


@pytest.mark.asyncio
async def test_confirmar_sem_data_e_rejeitado(auth_client):
    v = await _venda(auth_client)
    r = await auth_client.patch(f"/accounting/sales/{v['id']}", json={"is_sold": True})
    assert r.status_code == 422, r.text
    assert "data" in r.text.lower()


@pytest.mark.asyncio
async def test_confirmar_com_data_nula_explicita_e_rejeitado(auth_client):
    v = await _venda(auth_client)
    r = await auth_client.patch(f"/accounting/sales/{v['id']}",
                                json={"is_sold": True, "sold_at": None})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_data_informada_e_gravada_sem_substituicao(auth_client):
    v = await _venda(auth_client)
    r = await auth_client.patch(f"/accounting/sales/{v['id']}",
                                json={"is_sold": True, "sold_at": "2026-03-15"})
    assert r.status_code == 200, r.text
    assert r.json()["sold_at"] == "2026-03-15"


@pytest.mark.asyncio
async def test_receita_ainda_ganha_default_do_total(auth_client):
    """A receita tem palpite óbvio; a data não. Só a data virou obrigatória."""
    v = await _venda(auth_client)
    r = await auth_client.patch(f"/accounting/sales/{v['id']}",
                                json={"is_sold": True, "sold_at": "2026-03-15"})
    assert r.json()["confirmed_revenue"] == v["quote_total"]


@pytest.mark.asyncio
async def test_desmarcar_limpa_data_e_receita(auth_client):
    v = await _venda(auth_client)
    await auth_client.patch(f"/accounting/sales/{v['id']}",
                            json={"is_sold": True, "sold_at": "2026-03-15"})
    r = await auth_client.patch(f"/accounting/sales/{v['id']}", json={"is_sold": False})
    assert r.status_code == 200, r.text
    assert r.json()["sold_at"] is None
    assert r.json()["confirmed_revenue"] is None


@pytest.mark.asyncio
async def test_remarcar_apos_desmarcar_exige_data_de_novo(auth_client):
    """Regressão do estado fantasma: antes, remarcar ressuscitava a data velha."""
    v = await _venda(auth_client)
    await auth_client.patch(f"/accounting/sales/{v['id']}",
                            json={"is_sold": True, "sold_at": "2026-03-15"})
    await auth_client.patch(f"/accounting/sales/{v['id']}", json={"is_sold": False})
    r = await auth_client.patch(f"/accounting/sales/{v['id']}", json={"is_sold": True})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_patch_devolve_linha_completa(auth_client):
    """A tela usa a resposta do PATCH para atualizar a linha sem recarregar —
    se vier incompleta, as colunas esvaziam."""
    v = await _venda(auth_client)
    r = await auth_client.patch(f"/accounting/sales/{v['id']}",
                                json={"is_sold": True, "sold_at": "2026-03-15"})
    body = r.json()
    assert "itens_label" in body
    assert "client_name" in body
    assert isinstance(body["quote_seq"], int)
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/api/test_sale_date.py -v
```

Expected: FAIL — hoje o 422 não acontece, o desmarcar não limpa e o PATCH devolve linha incompleta.

- [ ] **Step 3: Reescrever o teste legado**

Em `backend/tests/api/test_accounting.py`, substituir
`test_confirming_sale_backfills_revenue_and_date` (linha 39) por:

```python
@pytest.mark.asyncio
async def test_confirming_sale_requires_date_and_defaults_revenue(auth_client):
    """A receita ainda ganha default de quote_total; a DATA passou a ser
    obrigatória — antes era preenchida com hoje, escondido, e a venda caía
    no mês errado do DRE. Ver Spec 2 §4.1."""
    await _seed_commercial_quote()
    await auth_client.post("/accounting/sync")
    sale = (await auth_client.get("/accounting/sales")).json()[0]
    quote_total = sale["quote_total"]

    r = await auth_client.patch(f"/accounting/sales/{sale['id']}", json={
        "is_sold": True, "confirmed_revenue": None, "sold_at": None,
    })
    assert r.status_code == 422, r.text

    r = await auth_client.patch(f"/accounting/sales/{sale['id']}", json={
        "is_sold": True, "confirmed_revenue": None, "sold_at": "2026-06-10",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_sold"] is True
    assert body["confirmed_revenue"] == quote_total
    assert body["sold_at"] == "2026-06-10"
```

- [ ] **Step 4: Implementar**

Em `backend/api/routes/accounting.py`, `update_sale`:

```python
@router.patch("/sales/{sale_id}", response_model=SaleOut)
async def update_sale(
    sale_id: UUID, payload: SaleUpdate,
    _: User = Depends(require_user), session: AsyncSession = Depends(db_session),
):
    sale = await session.get(Sale, sale_id)
    if not sale:
        raise HTTPException(404)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(sale, k, v)

    if sale.is_sold:
        # A receita tem palpite óbvio (o total do orçamento); a data não.
        # Antes daqui, sold_at era preenchido com hoje em silêncio e a venda
        # caía no mês corrente do DRE mesmo tendo ocorrido em outro.
        if sale.confirmed_revenue is None:
            sale.confirmed_revenue = sale.quote_total
        if sale.sold_at is None:
            raise HTTPException(422, "informe a data da venda")
    else:
        # Desmarcar limpa: receita confirmada sem venda não significa nada, e
        # deixar a data para trás fazia remarcar ressuscitar o mês errado.
        sale.sold_at = None
        sale.confirmed_revenue = None

    await session.commit()
    await session.refresh(sale)
    return _sale_out(
        sale,
        await sale_items_label(session, sale),
        await _client_name(session, sale),
        quote_seq=await _quote_seq(session, sale.quote_id),
    )
```

Com o helper:

```python
async def _quote_seq(session: AsyncSession, quote_id: UUID) -> int:
    return (await session.execute(select(Quote.seq).where(Quote.id == quote_id))).scalar() or 0
```

- [ ] **Step 5: Rodar e confirmar que passa**

```bash
docker compose run --rm api pytest backend/tests/api/test_sale_date.py backend/tests/api/test_accounting.py -v
make test 2>&1 | tail -5
make lint
```

Expected: verde. Se algum teste **além** dos dois anunciados quebrar, é regressão — investigar antes de seguir.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routes/accounting.py backend/tests/api/
git commit -m "feat(contábil): data de venda é escolha explícita

Marcar vendido sem data agora dá 422 em vez de gravar hoje escondido.
Desmarcar limpa data e receita — conserta o fantasma que fazia remarcar
ressuscitar o mês errado no DRE. PATCH devolve a linha completa.

Reescreve test_confirming_sale_backfills_revenue_and_date, que afirmava
o comportamento antigo. Ver Spec 2 §4.1.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Fim do N+1 na listagem

**Files:**
- Modify: `backend/api/routes/accounting.py`
- Modify: `backend/core/accounting/facts.py` (se `sale_items_label` viver lá)
- Test: `backend/tests/api/test_sales_query_count.py`

**Interfaces:**
- Consumes: nada novo.
- Produces: listagem com número constante de queries.

- [ ] **Step 1: Escrever o teste que falha**

Create `backend/tests/api/test_sales_query_count.py`:

```python
"""A listagem de vendas não pode crescer em queries com o número de linhas.

Antes: sale_items_label e _client_name faziam uma query cada, por linha.
"""
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Client, Quote, User


async def _semear(n: int) -> None:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        for i in range(n):
            c = Client(name=f"cliente {i}")
            s.add(c)
            await s.flush()
            s.add(Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id, client_id=c.id,
                        status=QuoteStatus.APROVADO.value, markup_pct=Decimal("100"),
                        min_charge=Decimal("0")))
        await s.commit()


async def _contar_queries(auth_client, url: str) -> int:
    contador = {"n": 0}

    def antes(conn, cursor, statement, params, context, executemany):
        contador["n"] += 1

    event.listen(session_module.engine.sync_engine, "before_cursor_execute", antes)
    try:
        r = await auth_client.get(url)
        assert r.status_code == 200, r.text
    finally:
        event.remove(session_module.engine.sync_engine, "before_cursor_execute", antes)
    return contador["n"]


@pytest.mark.asyncio
async def test_queries_nao_crescem_com_o_numero_de_vendas(auth_client):
    await _semear(3)
    await auth_client.post("/accounting/sync")
    poucas = await _contar_queries(auth_client, "/accounting/sales?kind=commercial")

    await _semear(12)
    await auth_client.post("/accounting/sync")
    muitas = await _contar_queries(auth_client, "/accounting/sales?kind=commercial")

    assert muitas <= poucas + 2, (
        f"listagem passou de {poucas} para {muitas} queries ao quadruplicar as linhas"
    )
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/api/test_sales_query_count.py -v
```

Expected: FAIL — o número de queries cresce com as linhas.

- [ ] **Step 3: Implementar a resolução em lote**

Em `list_sales`, resolver os três dicionários antes do laço e passá-los adiante:

```python
    quote_ids = [s.quote_id for s in rows]
    client_ids = [s.client_id for s in rows if s.client_id]

    nomes = dict(
        (await session.execute(select(Client.id, Client.name).where(Client.id.in_(client_ids)))).all()
    ) if client_ids else {}

    seqs = dict(
        (await session.execute(select(Quote.id, Quote.seq).where(Quote.id.in_(quote_ids)))).all()
    ) if quote_ids else {}

    producoes = await _produced_on_map(session, quote_ids)
    rotulos = await _items_label_map(session, quote_ids)

    return [
        _sale_out(
            s,
            itens_label=rotulos.get(s.quote_id, ""),
            client_name=nomes.get(s.client_id),
            quote_seq=seqs.get(s.quote_id, 0),
            produced_on=producoes.get(s.quote_id),
        )
        for s in rows
    ]
```

`_items_label_map` é a versão em lote de `sale_items_label`. Ler a implementação atual antes de escrever a versão agregada, para produzir **exatamente o mesmo rótulo**:

```bash
grep -n "def sale_items_label" -A 25 backend/core/accounting/facts.py
```

A versão em lote agrupa por `quote_id` com uma query só sobre `quote_items` e monta o mesmo texto.

- [ ] **Step 4: Confirmar que o rótulo não mudou**

```bash
docker compose run --rm api pytest backend/tests/api/test_accounting.py backend/tests/core/test_accounting_facts.py -v
```

Expected: verde. Rótulo diferente quebraria estes testes.

- [ ] **Step 5: Rodar tudo**

```bash
docker compose run --rm api pytest backend/tests/api/test_sales_query_count.py -v
make test 2>&1 | tail -5
make lint
```

- [ ] **Step 6: Commit**

```bash
git add backend/api/routes/accounting.py backend/core/accounting/facts.py \
        backend/tests/api/test_sales_query_count.py
git commit -m "perf(contábil): listagem de vendas em número constante de queries

sale_items_label e client_name saem do laço. Teste trava a regressão.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: GET deixa de escrever

**Files:**
- Modify: `backend/api/routes/accounting.py`
- Modify: `backend/tests/api/test_accounting.py` (**ajusta** `test_sales_listed_after_sync_and_patch`)
- Test: `backend/tests/api/test_sales_get_is_readonly.py`

**Interfaces:**
- Consumes: `POST /accounting/sync`, que já existe e não era chamado por ninguém.
- Produces: `GET /accounting/sales` puramente de leitura.

- [ ] **Step 1: Escrever o teste que falha**

Create `backend/tests/api/test_sales_get_is_readonly.py`:

```python
"""GET não escreve. Antes, list_sales chamava sync_sales() com commit —
cada clique em 'vendido' recalculava o custo de todo orçamento aprovado.
"""
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, Sale, User


@pytest.mark.asyncio
async def test_get_sales_nao_materializa_venda(auth_client):
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        s.add(Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                    status=QuoteStatus.APROVADO.value, markup_pct=Decimal("100"),
                    min_charge=Decimal("0")))
        await s.commit()

    r = await auth_client.get("/accounting/sales")
    assert r.status_code == 200
    assert r.json() == [], "GET materializou a venda — deveria ser só leitura"

    await auth_client.post("/accounting/sync")
    assert len((await auth_client.get("/accounting/sales")).json()) == 1


@pytest.mark.asyncio
async def test_get_sales_nao_altera_updated_at(auth_client):
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        s.add(Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                    status=QuoteStatus.APROVADO.value, markup_pct=Decimal("100"),
                    min_charge=Decimal("0")))
        await s.commit()
    await auth_client.post("/accounting/sync")

    async with session_module.SessionFactory() as s:
        antes = (await s.execute(sa.select(Sale.updated_at))).scalars().all()
    await auth_client.get("/accounting/sales")
    async with session_module.SessionFactory() as s:
        depois = (await s.execute(sa.select(Sale.updated_at))).scalars().all()
    assert antes == depois
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/api/test_sales_get_is_readonly.py -v
```

Expected: FAIL — o GET materializa a venda.

- [ ] **Step 3: Remover o sync do GET**

Em `list_sales`, apagar a linha:

```python
    await sync_sales(session)  # lazy: materializa ao abrir a aba
```

Se o import de `sync_sales` ficar sem uso no módulo, o `ruff` acusa — `run_sync` ainda o usa, então deve continuar.

- [ ] **Step 4: Ajustar o teste legado**

Em `backend/tests/api/test_accounting.py`, `test_sales_listed_after_sync_and_patch`
(linha 21): trocar o comentário *"GET dispara o sync e materializa a venda"* e
inserir a chamada explícita antes do GET:

```python
    # O sync agora é explícito — o GET é só leitura (Spec 2 §6.1).
    await auth_client.post("/accounting/sync")
    r = await auth_client.get("/accounting/sales")
```

Conferir se as linhas 152 e 184 do mesmo arquivo também dependiam do sync
implícito e, em caso positivo, inserir a mesma chamada:

```bash
sed -n '145,190p' backend/tests/api/test_accounting.py
```

- [ ] **Step 5: Rodar tudo**

```bash
docker compose run --rm api pytest backend/tests/api/test_sales_get_is_readonly.py -v
make test 2>&1 | tail -5
make lint
```

Expected: verde.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routes/accounting.py backend/tests/api/
git commit -m "perf(contábil): GET /sales deixa de escrever

O sync vira explícito via POST /accounting/sync, que já existia e não era
usado. Antes, cada marcação de vendido recalculava o custo de todo
orçamento aprovado.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Sub-aba "Uso pessoal"

**Files:**
- Modify: `frontend/src/routes/accounting/+page.svelte`
- Test: `backend/tests/core/test_perda_vs_aba_pessoal.py`

**Interfaces:**
- Consumes: `GET /accounting/sales?kind=personal`, `SaleOut.produced_on`, `SaleOut.quote_seq`.
- Produces: nada.

- [ ] **Step 1: Escrever o teste de consistência com o DRE**

Create `backend/tests/core/test_perda_vs_aba_pessoal.py`:

```python
"""O rodapé da aba Uso pessoal tem que bater com perda_operacional do DRE.

Divergência aqui é bug: os dois usam o mesmo critério de período (data de
produção = menor consumed_at) e a mesma fonte (linhas Sale pessoais não
vendidas e não arquivadas).

Semeadura no mesmo padrão de test_dre_personal_unsold_is_operational_loss_full_cpv,
em backend/tests/core/test_accounting_dre.py.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.core.accounting.dre import compute_dre
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialConsumption, Quote, QuoteItem, Sale, Settings, Spool, User,
)

PERIODO_DE = date(2026, 9, 1)
PERIODO_ATE = date(2026, 9, 30)


@pytest.mark.asyncio
async def test_soma_da_aba_pessoal_bate_com_perda_operacional(auth_client):
    async with session_module.SessionFactory() as s:
        await s.merge(Settings(id=1, revenue_tax_pct=Decimal("0")))
        user = User(name="u", email="abapessoal@t.com", password_hash="x")
        s.add(user)
        await s.commit()

        # Pessoal produzido e NÃO vendido: entra na perda pelo CPV cheio (70).
        q_perdido = Quote(kind=QuoteKind.PERSONAL.value, user_id=user.id,
                          status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("0"),
                          min_charge=Decimal("0"))
        # Pessoal VENDIDO: sai da perda e vira receita.
        q_vendido = Quote(kind=QuoteKind.PERSONAL.value, user_id=user.id,
                          status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"),
                          min_charge=Decimal("0"))
        s.add_all([q_perdido, q_vendido])
        await s.commit()

        s.add(Sale(quote_id=q_perdido.id, quote_status="produzido", quote_kind="personal",
                   quote_total=Decimal("0"), cpv_calc=Decimal("70"), is_sold=False,
                   variable_costs=Decimal("0")))
        s.add(Sale(quote_id=q_vendido.id, quote_status="entregue", quote_kind="personal",
                   quote_total=Decimal("200"), cpv_calc=Decimal("40"), is_sold=True,
                   confirmed_revenue=Decimal("200"), variable_costs=Decimal("0"),
                   sold_at=date(2026, 9, 10)))

        item_perdido = QuoteItem(quote_id=q_perdido.id, name="p", gcode_meta={}, quantity=1)
        item_vendido = QuoteItem(quote_id=q_vendido.id, name="v", gcode_meta={}, quantity=1)
        spool = Spool(material_type="PLA", purchased_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("700"))
        s.add_all([item_perdido, item_vendido, spool])
        await s.commit()

        # A data de produção é o que atribui a linha ao período, nos dois lados.
        s.add(MaterialConsumption(quote_item_id=item_perdido.id, spool_id=spool.id,
                                  grams_used=Decimal("100"), unit_cost_snapshot=Decimal("0.50"),
                                  consumed_at=datetime(2026, 9, 12, tzinfo=timezone.utc)))
        s.add(MaterialConsumption(quote_item_id=item_vendido.id, spool_id=spool.id,
                                  grams_used=Decimal("80"), unit_cost_snapshot=Decimal("0.50"),
                                  consumed_at=datetime(2026, 9, 14, tzinfo=timezone.utc)))
        await s.commit()

    async with session_module.SessionFactory() as s:
        dre = await compute_dre(s, PERIODO_DE, PERIODO_ATE)

    # O vendido não entra na perda; só o não-vendido, pelo CPV cheio.
    assert dre["perda_operacional"] == Decimal("70.00")

    linhas = (await auth_client.get("/accounting/sales?kind=personal")).json()
    soma_aba = sum(
        (Decimal(linha["cpv_override"] or linha["cpv_calc"])
         for linha in linhas
         if not linha["is_sold"] and not linha["is_stale"]
         and linha["produced_on"] is not None
         and PERIODO_DE <= date.fromisoformat(linha["produced_on"]) <= PERIODO_ATE),
        Decimal(0),
    )
    assert soma_aba == dre["perda_operacional"], (
        f"rodapé da aba ({soma_aba}) diverge do DRE ({dre['perda_operacional']})"
    )
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/core/test_perda_vs_aba_pessoal.py -v
```

- [ ] **Step 3: Implementar a sub-aba**

Em `accounting/+page.svelte`:

- O tipo `tab` ganha `"pessoal"`: `"vendas" | "pessoal" | "despesas" | "dre" | "lucratividade"`.
- O botão de sub-aba entra entre Vendas e Despesas; renumerar os `.idx` (`01`…`05`).
- A aba Vendas passa a pedir `?kind=commercial`; a nova pede `?kind=personal`.
- Colunas da nova: `#` (`quote_seq` → `quoteNumber`), Itens, Pessoas, Produzido em (`produced_on`), CPV, Estado.
- O contador do botão mostra a **perda do período**, não a contagem de linhas.
- Rodapé com o total de CPV das linhas não vendidas e não arquivadas cuja
  `produced_on` cai no período selecionado — exatamente o filtro do teste do Step 1.
- Ação por linha: "registrar como vendido", abrindo o mesmo popover da Task 7.
- Linha já vendida: badge "vendido" e CPV fora do total. **Não some da aba.**

O par de datas do DRE (`from`/`to`) vira estado compartilhado entre as sub-abas,
para que o rodapé use o mesmo período.

- [ ] **Step 4: Verificar**

```bash
cd frontend && npm run check && npm run build
cd .. && make test 2>&1 | tail -5
```

Abrir `/accounting`: a aba Vendas não mostra nenhum pessoal; a aba Uso pessoal
mostra os pessoais; o rodapé bate com a linha `perda_operacional` do DRE no mesmo
período.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/accounting/+page.svelte backend/tests/core/test_perda_vs_aba_pessoal.py
git commit -m "feat(contábil): sub-aba Uso pessoal

Tira o pessoal da lista de venda e lhe dá lugar próprio, com o total de
perda operacional do período. Teste trava a consistência com o DRE.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Popover de registro de venda

**Files:**
- Create: `frontend/src/lib/components/SaleEditor.svelte`
- Modify: `frontend/src/routes/accounting/+page.svelte`

**Interfaces:**
- Consumes: `action` de `$lib/resource`, `money`/`date` de `$lib/format`.
- Produces: componente com props `sale: Sale`, `pending: boolean`, e eventos `save` (`{ sold_at, confirmed_revenue }`) e `cancel`.

- [ ] **Step 1: Criar o componente**

Create `frontend/src/lib/components/SaleEditor.svelte`:

```svelte
<script lang="ts">
  import { createEventDispatcher } from "svelte";
  import type { Sale } from "$lib/types";

  export let sale: Sale;
  export let pending = false;

  const dispatch = createEventDispatcher<{
    save: { sold_at: string; confirmed_revenue: string };
    cancel: void;
  }>();

  const hoje = new Date().toISOString().slice(0, 10);
  let soldAt = sale.sold_at ?? hoje;
  let receita = String(sale.confirmed_revenue ?? sale.quote_total);

  const mesCorrente = hoje.slice(0, 7);
  // Editar uma venda para mês anterior mexe num DRE já fechado. É o
  // comportamento pedido, mas a pessoa precisa saber que está fazendo isso.
  $: avisaRetroativo = soldAt.slice(0, 7) < mesCorrente;
</script>

<div class="sale-editor" role="dialog" aria-label="Registrar venda">
  <label class="field">
    Data da venda
    <input type="date" bind:value={soldAt} required />
  </label>
  <label class="field">
    Receita confirmada
    <input type="number" step="0.01" min="0" bind:value={receita} />
  </label>
  {#if avisaRetroativo}
    <p class="hint warn">
      Esta data cai em mês anterior — o DRE daquele mês será recalculado.
    </p>
  {/if}
  <div class="actions">
    <button type="button" class="ghost tiny" on:click={() => dispatch("cancel")}>cancelar</button>
    <button
      type="button"
      class="tiny"
      disabled={pending || !soldAt}
      on:click={() => dispatch("save", { sold_at: soldAt, confirmed_revenue: receita })}
    >
      {pending ? "Salvando…" : "salvar"}
    </button>
  </div>
</div>

<style>
  .sale-editor {
    display: grid;
    gap: 0.6rem;
    padding: 0.9rem;
    border: 1px solid var(--line-strong);
    background: var(--paper);
    min-width: 15rem;
  }
  .actions {
    display: flex;
    gap: 0.5rem;
    justify-content: flex-end;
  }
  .hint.warn {
    color: var(--danger);
    margin: 0;
  }
</style>
```

- [ ] **Step 2: Ligar na página**

No slot `actions` da tabela de vendas (e da de pessoal), trocar o checkbox e o
input soltos por:

```svelte
      <svelte:fragment slot="actions" let:row>
        {@const s = row as Sale}
        {#if editandoId === s.id}
          <SaleEditor
            sale={s}
            pending={$saveSale.pending}
            on:save={(e) => registrarVenda(s, e.detail)}
            on:cancel={() => (editandoId = null)}
          />
        {:else if s.is_sold}
          <div class="sale-done mono">
            <span>{fmtDate(s.sold_at)}</span>
            <span>{money(s.confirmed_revenue)}</span>
            <button class="tiny ghost" on:click={() => (editandoId = s.id)}>editar</button>
            <button class="tiny ghost danger" on:click={() => desfazer(s)}>desfazer</button>
          </div>
        {:else}
          <button class="tiny" on:click={() => (editandoId = s.id)}>registrar venda</button>
        {/if}
      </svelte:fragment>
```

E as funções:

```ts
  let editandoId: string | null = null;

  async function registrarVenda(s: Sale, dados: { sold_at: string; confirmed_revenue: string }) {
    const atualizada = await saveSale.run(s.id, { is_sold: true, ...dados });
    if (!atualizada) return;                 // erro já exposto em $saveSale.error
    editandoId = null;
    trocarLinha(atualizada);                 // atualização otimista, sem reload
  }

  async function desfazer(s: Sale) {
    if (!confirm("Desfazer a venda apaga a data e a receita confirmada. Continuar?")) return;
    const atualizada = await saveSale.run(s.id, { is_sold: false });
    if (atualizada) trocarLinha(atualizada);
  }

  function trocarLinha(nova: Sale) {
    for (const r of [sales, pessoais]) {
      const atual = get(r).data ?? [];
      if (atual.some((x) => x.id === nova.id)) {
        r.set(atual.map((x) => (x.id === nova.id ? nova : x)));
      }
    }
  }
```

Importar `get` de `svelte/store`.

O `reload` após PATCH, mantido provisoriamente na Task 4 da Spec 0, sai aqui.

- [ ] **Step 3: Verificar**

```bash
cd frontend && npm run check && npm run build
```

Exercitar: registrar venda com data de hoje; registrar com data retroativa e
conferir o aviso; editar a data de uma venda já registrada; desfazer e confirmar
que a linha volta a "registrar venda"; tentar salvar sem data (o botão fica
desabilitado); provocar um 422 mandando data vazia via devtools e conferir que a
mensagem do backend aparece.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/SaleEditor.svelte frontend/src/routes/accounting/+page.svelte
git commit -m "feat(contábil): registro de venda com data escolhida

Checkbox solto vira popover com data e receita. Atualização otimista com
a resposta do PATCH — sem recarregar a lista inteira.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Busca, período e chips de status

**Files:**
- Modify: `frontend/src/routes/accounting/+page.svelte`

**Interfaces:**
- Consumes: `SearchBar`, `Table` com busca (Spec 1, Task 5).
- Produces: nada.

- [ ] **Step 1: Busca nas três listas**

Adicionar um `SearchBar` acima de cada tabela (Vendas, Uso pessoal, Despesas),
com estado próprio por aba, e passar `searchText` e `searchExtra` para a `Table`:

```svelte
<SearchBar bind:value={buscaVendas}
           total={vendasFiltradas.length} shown={vendasMostradas}
           placeholder="buscar por número, cliente, peça ou nota…" />
```

`searchExtra` para vendas e pessoal devolve `notes`; para despesas, a categoria
já é coluna, então não precisa de extra.

- [ ] **Step 2: Chips de status em Vendas**

Substituir o checkbox "mostrar arquivadas" por quatro chips:
`todos · a confirmar · vendidos · arquivados`. O filtro é client-side sobre
`is_sold` e `is_stale`. Estado inicial: `a confirmar` — é a razão de abrir a aba.

Remover o parâmetro `is_stale=false` da URL: agora a lista traz tudo do tipo e os
chips filtram na tela. Conferir que isso não estoura o volume — se um dia
estourar, o chip volta a ser parâmetro de API.

- [ ] **Step 3: Período em Vendas**

Reaproveitar o par `from`/`to` já elevado a estado compartilhado na Task 6.
Filtrar as vendas por `sold_at` dentro do período — linhas sem `sold_at`
(ainda não vendidas) aparecem sempre, senão o chip "a confirmar" esvaziaria.

- [ ] **Step 4: Verificar**

```bash
cd frontend && npm run check && npm run build && npm test
cd .. && make test 2>&1 | tail -5 && make lint && make e2e
```

Exercitar cada filtro e a combinação deles.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/accounting/+page.svelte
git commit -m "feat(contábil): busca, período e chips de status

Chips substituem o checkbox 'mostrar arquivadas' — um controle de duas
posições fazendo o trabalho de quatro.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: E2E da venda retroativa

**Files:**
- Create: `tests/e2e/venda-retroativa.spec.ts`

**Interfaces:**
- Consumes: tudo acima.
- Produces: nada.

- [ ] **Step 1: Escrever o teste**

O fluxo: criar orçamento comercial, aprovar, sincronizar o contábil, registrar a
venda com data de dois meses atrás, abrir o DRE daquele mês e conferir que a
receita aparece lá — e **não** no mês corrente.

Ler `tests/e2e/` antes para reusar os helpers de login e criação de orçamento que
já existem, em vez de reescrevê-los.

- [ ] **Step 2: Rodar**

```bash
make up && make seed && make e2e
```

Expected: verde.

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/venda-retroativa.spec.ts
git commit -m "test(e2e): venda com data retroativa cai no DRE do mês certo

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Critério de pronto da Spec 2

- [ ] `make test`, `make lint`, `make e2e` verdes.
- [ ] Aba Vendas não mostra nenhum orçamento pessoal.
- [ ] Nenhuma venda é registrada sem data escolhida por uma pessoa (422 cobre).
- [ ] Desmarcar limpa data e receita; remarcar exige data de novo.
- [ ] As três listas têm busca; Vendas tem período e chips de status.
- [ ] `GET /accounting/sales` não escreve, verificado por teste.
- [ ] Contagem de queries da listagem não cresce com as linhas.
- [ ] Total da aba Uso pessoal bate com `perda_operacional` do DRE.
- [ ] Exatamente dois testes legados alterados, ambos anunciados no topo deste plano.
