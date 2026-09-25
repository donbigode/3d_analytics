# Spec 1 — Plataforma: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar ao orçamento um número legível por humanos, e a todas as listas do app busca, ordenação e um layout que funciona no celular.

**Architecture:** Uma coluna `quotes.seq` alimentada por sequence Postgres, com backfill cronológico; a lógica de ordenar e filtrar extraída para um módulo puro (`$lib/table-logic.ts`) que a `Table.svelte` consome — puro para ser testável sem DOM; modo card na `Table` abaixo de 700px reusando as mesmas `columns`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, pytest, SvelteKit 2 + Svelte 5, TypeScript, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-21-plataforma-numeracao-busca-design.md`

## Global Constraints

- **Depende da Spec 0 concluída** — `$lib/format`, `$lib/resource` e o pacote `quotes/` precisam existir.
- Migração `0032_quote_seq` é a **única com backfill real** das quatro specs. Deve ser compatível com a API anterior rodando (a coluna tem default).
- Numeração **global**, não por tipo. Formato de exibição: `#` + `padStart(4, "0")`.
- O UUID continua sendo a chave em toda URL e chamada de API. Nada roteia por `seq`.
- Busca e ordenação são **client-side**. Nenhum endpoint novo.
- Tudo roda via Docker Compose: `make test`, `make lint`, `make e2e`.
- Mensagens de commit terminam com `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

### Task 1: Migração `0032_quote_seq`

**Files:**
- Create: `migrations/versions/0032_quote_seq.py`
- Modify: `backend/infra/db/models/quote.py`
- Test: `backend/tests/api/test_quote_seq.py`

**Interfaces:**
- Consumes: nada.
- Produces: `Quote.seq: Mapped[int]` — inteiro, não nulo, único, preenchido pelo banco.

- [ ] **Step 1: Escrever o teste que falha**

Create `backend/tests/api/test_quote_seq.py`:

```python
"""Numeração humana dos orçamentos (#0042).

A suíte roda as migrações contra o banco de teste, então o backfill já
aconteceu quando estes testes rodam — o que eles verificam é o
comportamento da coluna daí em diante.
"""
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, User


async def _novo_quote(status=QuoteStatus.DRAFT) -> Quote:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id, status=status.value,
                  markup_pct=Decimal("100"), min_charge=Decimal("0"))
        s.add(q)
        await s.commit()
        await s.refresh(q)
        return q


@pytest.mark.asyncio
async def test_seq_e_atribuido_pelo_banco_sem_passar_o_campo(auth_client):
    q = await _novo_quote()
    assert q.seq is not None
    assert q.seq > 0


@pytest.mark.asyncio
async def test_seq_incrementa_a_cada_orcamento(auth_client):
    a = await _novo_quote()
    b = await _novo_quote()
    assert b.seq == a.seq + 1


@pytest.mark.asyncio
async def test_seq_e_unico(auth_client):
    a = await _novo_quote()
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        dup = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                    status=QuoteStatus.DRAFT.value, markup_pct=Decimal("0"),
                    min_charge=Decimal("0"), seq=a.seq)
        s.add(dup)
        with pytest.raises(Exception):
            await s.commit()


@pytest.mark.asyncio
async def test_seq_sobrevive_a_delecao_sem_reaproveitar(auth_client):
    a = await _novo_quote()
    async with session_module.SessionFactory() as s:
        obj = await s.get(Quote, a.id)
        await s.delete(obj)
        await s.commit()
    b = await _novo_quote()
    assert b.seq > a.seq


@pytest.mark.asyncio
async def test_criar_via_api_devolve_seq(auth_client):
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    assert r.status_code == 201, r.text
    assert isinstance(r.json()["seq"], int)
    assert r.json()["seq"] > 0
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_seq.py -v
```

Expected: FAIL — `Quote` não tem atributo `seq`.

- [ ] **Step 3: Escrever a migração**

Create `migrations/versions/0032_quote_seq.py`:

```python
"""quotes.seq — número humano do orçamento (#0042)

Backfill cronológico: numera o histórico existente por created_at, com o
id como desempate determinístico. A sequence assume dali em diante.

A coluna nasce com DEFAULT, então uma API da versão anterior continua
inserindo orçamentos sem erro — a migração pode subir antes do deploy.

Revision ID: 0032_quote_seq
Revises: 0031_printer_job_spool
Create Date: 2026-09-21 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032_quote_seq"
down_revision: Union[str, Sequence[str], None] = "0031_printer_job_spool"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quotes", sa.Column("seq", sa.Integer(), nullable=True))
    op.execute("CREATE SEQUENCE quote_seq")
    op.execute(
        """
        WITH ord AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM quotes
        )
        UPDATE quotes q SET seq = ord.rn FROM ord WHERE q.id = ord.id
        """
    )
    op.execute(
        "SELECT setval('quote_seq', COALESCE((SELECT MAX(seq) FROM quotes), 0) + 1, false)"
    )
    op.alter_column("quotes", "seq", nullable=False,
                    server_default=sa.text("nextval('quote_seq')"))
    op.create_index("ix_quotes_seq", "quotes", ["seq"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_quotes_seq", table_name="quotes")
    op.drop_column("quotes", "seq")
    op.execute("DROP SEQUENCE IF EXISTS quote_seq")
```

- [ ] **Step 4: Adicionar o campo ao modelo**

Em `backend/infra/db/models/quote.py`, depois de `id`:

```python
    # Número humano do orçamento (#0042). Preenchido pelo banco via sequence;
    # nunca passado pela aplicação. O id (UUID) segue sendo a chave.
    seq: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=True,
        server_default=sa.text("nextval('quote_seq')"),
    )
```

Acrescentar `Integer` ao import de `sqlalchemy` no topo do arquivo e importar `sqlalchemy as sa`.

- [ ] **Step 5: Rodar e confirmar que passa**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_seq.py -v
```

Expected: 4 dos 5 passam. `test_criar_via_api_devolve_seq` ainda falha — `QuoteOut` não tem `seq` (Task 2).

- [ ] **Step 6: Verificar o backfill num banco com dados**

O banco de teste é recriado do zero, então o backfill roda sobre tabela vazia. Testar com dados de verdade:

```bash
docker compose run --rm api alembic downgrade 0031_printer_job_spool
docker compose run --rm api python -c "
import asyncio, sqlalchemy as sa
from backend.infra.db.session import SessionFactory
async def main():
    async with SessionFactory() as s:
        n = (await s.execute(sa.text('SELECT count(*) FROM quotes'))).scalar()
        print('orçamentos no banco de dev:', n)
asyncio.run(main())
"
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -c "
import asyncio, sqlalchemy as sa
from backend.infra.db.session import SessionFactory
async def main():
    async with SessionFactory() as s:
        rows = (await s.execute(sa.text(
            'SELECT seq, created_at FROM quotes ORDER BY seq'))).all()
        seqs = [r[0] for r in rows]
        assert seqs == list(range(1, len(seqs) + 1)), f'buracos: {seqs}'
        datas = [r[1] for r in rows]
        assert datas == sorted(datas), 'seq fora da ordem cronológica'
        print('backfill ok:', len(seqs), 'orçamentos numerados 1..N')
asyncio.run(main())
"
```

Expected: `backfill ok: N orçamentos numerados 1..N`.

- [ ] **Step 7: Verificar que o downgrade limpa tudo**

```bash
docker compose run --rm api alembic downgrade 0031_printer_job_spool
docker compose run --rm api python -c "
import asyncio, sqlalchemy as sa
from backend.infra.db.session import SessionFactory
async def main():
    async with SessionFactory() as s:
        r = await s.execute(sa.text(
            \"SELECT 1 FROM information_schema.columns \"
            \"WHERE table_name='quotes' AND column_name='seq'\"))
        assert r.first() is None, 'coluna seq sobreviveu ao downgrade'
        r = await s.execute(sa.text(
            \"SELECT 1 FROM information_schema.sequences WHERE sequence_name='quote_seq'\"))
        assert r.first() is None, 'sequence sobreviveu ao downgrade'
        print('downgrade limpo')
asyncio.run(main())
"
docker compose run --rm api alembic upgrade head
```

Expected: `downgrade limpo`.

- [ ] **Step 8: Commit**

```bash
git add migrations/versions/0032_quote_seq.py backend/infra/db/models/quote.py \
        backend/tests/api/test_quote_seq.py
git commit -m "feat(db): quotes.seq — número humano com backfill cronológico

Sequence Postgres resolve inserção concorrente. Backfill numera o
histórico por created_at. Coluna com DEFAULT: compatível com a API
anterior, sobe sem janela de indisponibilidade.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `seq` na API

**Files:**
- Modify: `backend/api/schemas/quotes.py`
- Modify: `backend/api/routes/quotes/_shared.py` (`_quote_out`)
- Modify: `backend/api/schemas/accounting.py`
- Modify: `backend/api/routes/accounting.py` (`_sale_out`, `list_sales`)
- Test: `backend/tests/api/test_quote_seq.py` (estende)

**Interfaces:**
- Consumes: `Quote.seq` (Task 1).
- Produces: `QuoteOut.seq: int` e `SaleOut.quote_seq: int`. A Spec 2 e a Spec 3 dependem dos dois.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar a `backend/tests/api/test_quote_seq.py`:

```python
@pytest.mark.asyncio
async def test_listagem_de_quotes_traz_seq(auth_client):
    await auth_client.post("/quotes", json={"kind": "commercial"})
    r = await auth_client.get("/quotes")
    assert r.status_code == 200
    assert all(isinstance(q["seq"], int) for q in r.json())


@pytest.mark.asyncio
async def test_sale_out_traz_quote_seq(auth_client):
    q = await _novo_quote(status=QuoteStatus.APROVADO)
    r = await auth_client.get("/accounting/sales")
    assert r.status_code == 200, r.text
    venda = next(v for v in r.json() if v["quote_id"] == str(q.id))
    assert venda["quote_seq"] == q.seq
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_seq.py -v
```

Expected: FAIL — `KeyError: 'seq'` e `KeyError: 'quote_seq'`.

- [ ] **Step 3: Adicionar `seq` ao `QuoteOut`**

Em `backend/api/schemas/quotes.py`, na classe `QuoteOut`, logo após `id`:

```python
    seq: int
```

Em `_quote_out` (agora em `backend/api/routes/quotes/_shared.py`), incluir `seq=q.seq` na construção do `QuoteOut`.

- [ ] **Step 4: Adicionar `quote_seq` ao `SaleOut`**

Em `backend/api/schemas/accounting.py`, na classe `SaleOut`, após `quote_id`:

```python
    quote_seq: int
```

Em `backend/api/routes/accounting.py`, `_sale_out` ganha o parâmetro e `list_sales` o resolve **em lote**, não por linha:

```python
def _sale_out(s: Sale, itens_label: str = "", client_name: str | None = None,
              quote_seq: int = 0) -> SaleOut:
    return SaleOut(
        id=str(s.id), quote_id=str(s.quote_id), quote_seq=quote_seq,
        # ...demais campos exatamente como já estão no arquivo, sem alteração
    )
```

Em `list_sales`, antes do return:

```python
    seq_por_quote = dict(
        (await session.execute(
            select(Quote.id, Quote.seq).where(Quote.id.in_([s.quote_id for s in rows]))
        )).all()
    )
```

E usar `quote_seq=seq_por_quote.get(s.quote_id, 0)` na construção de cada linha. Importar `Quote` de `backend.infra.db.models`.

Em `update_sale`, buscar o `seq` do orçamento da venda antes do return.

- [ ] **Step 5: Rodar e confirmar que passa**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_seq.py -v
make test 2>&1 | tail -5
make lint
```

Expected: todos verdes.

- [ ] **Step 6: Atualizar os tipos do frontend**

Em `frontend/src/lib/types.ts`, adicionar `seq: number` a `Quote` e `quote_seq: number` a `Sale`.

```bash
cd frontend && npm run check
```

Expected: sem erro.

- [ ] **Step 7: Commit**

```bash
git add backend/api/schemas/ backend/api/routes/ backend/tests/api/test_quote_seq.py \
        frontend/src/lib/types.ts
git commit -m "feat(api): QuoteOut.seq e SaleOut.quote_seq

quote_seq resolvido em lote na listagem de vendas — não reintroduz N+1.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Exibir `#0042` em todas as superfícies

**Files:**
- Create: `frontend/src/lib/quote-number.ts`
- Test: `frontend/src/lib/quote-number.test.ts`
- Modify: `frontend/src/routes/quotes/+page.svelte`
- Modify: `frontend/src/routes/quotes/[id]/+page.svelte`
- Modify: `frontend/src/routes/accounting/+page.svelte`
- Modify: `frontend/src/routes/inbox/+page.svelte`
- Modify: `frontend/src/routes/capacity/+page.svelte`
- Modify: `backend/infra/pdf/templates/quote.html`

**Interfaces:**
- Consumes: `QuoteOut.seq`, `SaleOut.quote_seq` (Task 2).
- Produces: `export function quoteNumber(seq: number | null | undefined): string`.

- [ ] **Step 1: Escrever o teste que falha**

Create `frontend/src/lib/quote-number.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { quoteNumber } from "./quote-number";

describe("quoteNumber", () => {
  it("formata com quatro dígitos", () => {
    expect(quoteNumber(42)).toBe("#0042");
  });
  it("não trunca acima de 9999", () => {
    expect(quoteNumber(12345)).toBe("#12345");
  });
  it("formata o primeiro orçamento", () => {
    expect(quoteNumber(1)).toBe("#0001");
  });
  it("devolve travessão para ausente", () => {
    expect(quoteNumber(null)).toBe("—");
    expect(quoteNumber(undefined)).toBe("—");
  });
});
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd frontend && npm test
```

Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar**

Create `frontend/src/lib/quote-number.ts`:

```ts
import { DASH } from "$lib/format";

/** Número humano do orçamento. O UUID segue sendo a chave em URLs e na API;
 *  isto é só o que a pessoa lê e fala em voz alta. */
export function quoteNumber(seq: number | null | undefined): string {
  if (seq === null || seq === undefined || !Number.isFinite(seq)) return DASH;
  return `#${String(seq).padStart(4, "0")}`;
}
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd frontend && npm test
```

Expected: PASS.

- [ ] **Step 5: Trocar nas telas**

Em `quotes/+page.svelte`, a célula `#`:

```svelte
            <td class="mono" title={q.id}>{quoteNumber(q.seq)}</td>
```

Em `accounting/+page.svelte`, a coluna `quote_id` vira:

```ts
        { key: "quote_seq", label: "Orçamento", mono: true,
          format: (v) => quoteNumber(v as number) },
```

Em `quotes/[id]/+page.svelte`, o título da página passa a incluir o número.

Em `inbox/` e `capacity/`, trocar onde hoje aparece `uuid.slice(0, 8)` de orçamento. Localizar com:

```bash
cd /Users/orochage/Codes/3d_analytics
grep -rn "slice(0, 8)\|slice(0,8)" frontend/src/routes/
```

Cada ocorrência que se refere a um **orçamento** troca; as que se referem a spool, job de impressora ou outro id ficam como estão (não têm número humano).

- [ ] **Step 6: Trocar no PDF**

Em `backend/infra/pdf/templates/quote.html`, adicionar o número ao cabeçalho. Ler o template antes para achar onde o identificador aparece hoje e qual variável de contexto está disponível; se `quote` já está no contexto, é `{{ "#%04d"|format(quote.seq) }}`.

Conferir o que a rota de PDF passa no contexto:

```bash
grep -n "TemplateResponse\|render\|context" backend/api/routes/quotes/pdf.py
```

Aproveitar a passada no template para consolidar as macros de moeda e data em
`_base.html`, como a Spec 0 §6 prevê — hoje a formatação pt-BR do PDF é feita
inline, em paralelo à do frontend. Definir uma vez:

```jinja
{% macro brl(v) %}R$ {{ "%.2f"|format(v|float)|replace(".", ",") }}{% endmacro %}
{% macro dma(d) %}{{ d.strftime("%d/%m/%Y") if d else "—" }}{% endmacro %}
{% macro numero(seq) %}#{{ "%04d"|format(seq) }}{% endmacro %}
```

e importá-las em `quote.html` com `{% from "_base.html" import brl, dma, numero %}`,
trocando as formatações inline existentes. Rodar
`docker compose run --rm api pytest backend/tests/api/test_quotes_pdf.py -v`
depois — o PDF não pode mudar de conteúdo, só de implementação.

- [ ] **Step 7: Verificar**

```bash
cd frontend && npm run check && npm run build
cd .. && make test 2>&1 | tail -5
```

Abrir `/quotes`, `/accounting`, um orçamento, `/inbox`, `/capacity` e gerar um PDF. Nenhuma tela deve exibir UUID cru.

```bash
grep -rn "slice(0, 8)\|slice(0,8)" frontend/src/routes/
```

Expected: só ocorrências de ids que não são de orçamento.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/quote-number.ts frontend/src/lib/quote-number.test.ts \
        frontend/src/routes/ backend/infra/pdf/templates/quote.html
git commit -m "feat(ui): orçamento exibido como #0042 em todas as superfícies

UUID sai da tela e vira title=. Continua sendo a chave em URL e API.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `table-logic.ts` — ordenar e filtrar

A lógica sai da `Table.svelte` para um módulo puro. Motivo duplo: fica testável sem DOM (o Vitest da Spec 0 roda em `node`, sem jsdom) e a `Table` fica só com renderização.

**Files:**
- Create: `frontend/src/lib/table-logic.ts`
- Test: `frontend/src/lib/table-logic.test.ts`

**Interfaces:**
- Consumes: nada.
- Produces:
  ```ts
  export type Row = Record<string, unknown>;
  export type SortDir = "asc" | "desc" | null;
  export function normalize(s: string): string;
  export function compareValues(a: unknown, b: unknown): number;
  export function sortRows(rows: Row[], key: string | null, dir: SortDir): Row[];
  export function filterRows(
    rows: Row[], text: string,
    haystack: (row: Row) => string,
  ): Row[];
  export function nextDir(current: SortDir): SortDir;  // asc → desc → null → asc
  ```

- [ ] **Step 1: Escrever o teste que falha**

Create `frontend/src/lib/table-logic.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { normalize, compareValues, sortRows, filterRows, nextDir } from "./table-logic";

describe("normalize", () => {
  it("remove acento e caixa", () => {
    expect(normalize("Orçamento PÚBLICO")).toBe("orcamento publico");
  });
  it("aguenta string vazia", () => {
    expect(normalize("")).toBe("");
  });
});

describe("compareValues", () => {
  it("compara números como números, não como texto", () => {
    expect(compareValues(9, 10)).toBeLessThan(0);
  });
  it("compara string numérica da API como número", () => {
    // Decimal serializado pelo backend chega como string
    expect(compareValues("9.00", "10.00")).toBeLessThan(0);
  });
  it("compara data ISO cronologicamente", () => {
    expect(compareValues("2026-09-02", "2026-09-10")).toBeLessThan(0);
  });
  it("compara texto com localeCompare pt-BR", () => {
    expect(compareValues("ácido", "azul")).toBeLessThan(0);
  });
  it("põe nulo por último", () => {
    expect(compareValues(null, 1)).toBeGreaterThan(0);
    expect(compareValues(1, null)).toBeLessThan(0);
  });
});

describe("sortRows", () => {
  const rows = [{ n: 10, s: "b" }, { n: 9, s: "a" }, { n: 11, s: "c" }];

  it("ordena crescente", () => {
    expect(sortRows(rows, "n", "asc").map((r) => r.n)).toEqual([9, 10, 11]);
  });
  it("ordena decrescente", () => {
    expect(sortRows(rows, "n", "desc").map((r) => r.n)).toEqual([11, 10, 9]);
  });
  it("devolve a ordem natural quando dir é null", () => {
    expect(sortRows(rows, "n", null).map((r) => r.n)).toEqual([10, 9, 11]);
  });
  it("não muta o array original", () => {
    sortRows(rows, "n", "asc");
    expect(rows.map((r) => r.n)).toEqual([10, 9, 11]);
  });
});

describe("filterRows", () => {
  const rows = [
    { id: 1, texto: "R$ 1.234,56 · Maria Silva" },
    { id: 2, texto: "R$ 99,00 · João Ançã" },
  ];
  const hay = (r: Record<string, unknown>) => String(r.texto);

  it("casa sobre o valor formatado", () => {
    expect(filterRows(rows, "1.234", hay).map((r) => r.id)).toEqual([1]);
  });
  it("ignora acento e caixa", () => {
    expect(filterRows(rows, "anca", hay).map((r) => r.id)).toEqual([2]);
    expect(filterRows(rows, "MARIA", hay).map((r) => r.id)).toEqual([1]);
  });
  it("texto vazio devolve tudo", () => {
    expect(filterRows(rows, "", hay)).toHaveLength(2);
  });
  it("sem casamento devolve vazio", () => {
    expect(filterRows(rows, "zzz", hay)).toHaveLength(0);
  });
});

describe("nextDir", () => {
  it("cicla asc → desc → null → asc", () => {
    expect(nextDir(null)).toBe("asc");
    expect(nextDir("asc")).toBe("desc");
    expect(nextDir("desc")).toBe(null);
  });
});
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
cd frontend && npm test
```

Expected: FAIL — módulo não existe.

- [ ] **Step 3: Implementar**

Create `frontend/src/lib/table-logic.ts`:

```ts
/** Ordenação e filtro das tabelas do app.
 *
 *  Módulo puro de propósito: testável sem DOM, e mantém a Table.svelte
 *  só com renderização.
 *
 *  Regra central da ordenação: compara o valor BRUTO, nunca o formatado —
 *  "R$ 1.234,56" ordenado como texto põe 9 depois de 10. Já o FILTRO
 *  casa sobre o formatado, porque o usuário busca o que está vendo. */

export type Row = Record<string, unknown>;
export type SortDir = "asc" | "desc" | null;

const ISO_DATE = /^\d{4}-\d{2}-\d{2}/;

export function normalize(s: string): string {
  return s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

function asNumber(v: unknown): number | null {
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string" && v.trim() !== "" && !ISO_DATE.test(v)) {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

export function compareValues(a: unknown, b: unknown): number {
  const aVazio = a === null || a === undefined || a === "";
  const bVazio = b === null || b === undefined || b === "";
  if (aVazio && bVazio) return 0;
  if (aVazio) return 1;   // ausente sempre por último
  if (bVazio) return -1;

  const na = asNumber(a);
  const nb = asNumber(b);
  if (na !== null && nb !== null) return na - nb;

  const sa = String(a);
  const sb = String(b);
  if (ISO_DATE.test(sa) && ISO_DATE.test(sb)) return sa < sb ? -1 : sa > sb ? 1 : 0;

  return sa.localeCompare(sb, "pt-BR", { numeric: true, sensitivity: "base" });
}

export function sortRows(rows: Row[], key: string | null, dir: SortDir): Row[] {
  if (!key || dir === null) return rows;
  const fator = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => fator * compareValues(a[key], b[key]));
}

export function filterRows(rows: Row[], text: string, haystack: (row: Row) => string): Row[] {
  const alvo = normalize(text.trim());
  if (!alvo) return rows;
  return rows.filter((r) => normalize(haystack(r)).includes(alvo));
}

export function nextDir(current: SortDir): SortDir {
  return current === null ? "asc" : current === "asc" ? "desc" : null;
}
```

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
cd frontend && npm test
```

Expected: PASS, 19 testes novos.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/table-logic.ts frontend/src/lib/table-logic.test.ts
git commit -m "feat(frontend): table-logic.ts — ordenação e filtro puros

Ordena sobre o valor bruto, filtra sobre o formatado. Módulo puro para
ser testável sem DOM.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `SearchBar.svelte` e `Table.svelte` com busca e ordenação

**Files:**
- Create: `frontend/src/lib/components/SearchBar.svelte`
- Modify: `frontend/src/lib/components/Table.svelte`

**Interfaces:**
- Consumes: `table-logic.ts` (Task 4).
- Produces:
  - `SearchBar`: props `value` (bindable), `total`, `shown`, `placeholder`.
  - `Table`: props novas `searchText: string`, `searchExtra?: (row) => string`, e `sortable?: boolean` em cada item de `columns`.

- [ ] **Step 1: Criar o `SearchBar`**

Create `frontend/src/lib/components/SearchBar.svelte`:

```svelte
<script lang="ts">
  export let value = "";
  export let total = 0;
  export let shown = 0;
  export let placeholder = "buscar…";

  let raw = value;
  let timer: ReturnType<typeof setTimeout>;

  function onInput(e: Event) {
    raw = (e.currentTarget as HTMLInputElement).value;
    clearTimeout(timer);
    timer = setTimeout(() => (value = raw), 150);
  }
  function limpar() {
    raw = "";
    clearTimeout(timer);
    value = "";
  }
</script>

<div class="searchbar">
  <input type="search" {placeholder} value={raw} on:input={onInput} aria-label={placeholder} />
  {#if value}
    <span class="counter mono">{shown} de {total}</span>
    <button type="button" class="tiny ghost" on:click={limpar}>limpar</button>
  {/if}
</div>

<style>
  .searchbar {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    flex-wrap: wrap;
  }
  .searchbar input {
    flex: 1 1 14rem;
    min-height: 44px;
    padding: 0.5rem 0.7rem;
    border: 1px solid var(--line-strong);
    background: var(--paper);
    font-family: inherit;
    font-size: 0.92rem;
  }
  .counter {
    font-size: 0.72rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
    white-space: nowrap;
  }
</style>
```

- [ ] **Step 2: Estender a `Table`**

Em `frontend/src/lib/components/Table.svelte`, no `<script>`:

```ts
  import { sortRows, filterRows, nextDir, type SortDir } from "$lib/table-logic";

  export let searchText = "";
  export let searchExtra: ((row: Row) => string) | undefined = undefined;

  let sortKey: string | null = null;
  let sortDir: SortDir = null;

  function toggleSort(key: string) {
    if (sortKey !== key) { sortKey = key; sortDir = "asc"; return; }
    sortDir = nextDir(sortDir);
    if (sortDir === null) sortKey = null;
  }

  // O filtro casa sobre o texto já formatado de todas as colunas, mais o
  // que searchExtra trouxer (notas e afins, que não são coluna).
  function haystack(row: Row): string {
    const cols = columns.map((c) => display(c, row)).join(" ");
    return searchExtra ? `${cols} ${searchExtra(row)}` : cols;
  }

  $: visible = sortRows(filterRows(rows, searchText, haystack), sortKey, sortDir);
```

No markup, trocar `{#each rows as row}` por `{#each visible as row}` e o `colspan` do vazio, e tornar o `th` clicável quando `c.sortable`:

```svelte
        {#each columns as c}
          <th class:right={c.align === "right"} class:center={c.align === "center"}
              style:width={c.width ?? "auto"}>
            {#if c.sortable}
              <button type="button" class="sort" on:click={() => toggleSort(c.key)}>
                <span>{c.label}</span>
                <span class="dir" aria-hidden="true"
                  >{sortKey === c.key ? (sortDir === "asc" ? "↑" : "↓") : ""}</span>
              </button>
            {:else}
              <span>{c.label}</span>
            {/if}
          </th>
        {/each}
```

Adicionar `sortable?: boolean` ao tipo de `columns` e o estilo do botão (herda a tipografia do `th`, sem borda nem fundo, `min-height: 44px`).

Quando `searchText` filtra tudo, o `empty` precisa dizer outra coisa que "Nenhum registro":

```svelte
          <td colspan={columns.length + ($$slots.actions ? 1 : 0)}>
            <div class="empty">{searchText ? "Nada encontrado para a busca" : empty}</div>
          </td>
```

- [ ] **Step 3: Verificar tipos e build**

```bash
cd frontend && npm run check && npm run build
```

Expected: sem erro. As páginas que já usam `Table` continuam funcionando — as props novas têm default.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/components/
git commit -m "feat(ui): SearchBar + Table com busca e ordenação por coluna

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Aplicar busca e ordenação nas listas

**Files:**
- Modify: `frontend/src/routes/quotes/+page.svelte`
- Modify: `frontend/src/routes/clients/+page.svelte`
- Modify: `frontend/src/routes/spools/+page.svelte`
- Modify: `frontend/src/routes/materials/+page.svelte`
- Modify: `frontend/src/routes/library/+page.svelte`

O Contábil fica de fora — é a Spec 2 que o reescreve, e mexer nele aqui geraria conflito.

**Interfaces:**
- Consumes: `SearchBar`, `Table` (Task 5).
- Produces: nada.

- [ ] **Step 1: Converter `quotes/+page.svelte` para a `Table`**

A página hoje monta a tabela na mão (markup próprio, não usa o componente). Converter para `Table` com `columns`, marcando `sortable` em `#`, Tipo, Status, Cliente, Total e Criado.

A coluna Tipo tem markup rico (tag + chips de pessoa) e Ações também — vão pelo slot `actions` e por um slot de célula, ou ficam como colunas simples com o conteúdo rico movido para o slot. Decidir ao converter; o critério é não perder os chips de atribuição de pessoa.

Adicionar acima da tabela:

```svelte
<SearchBar bind:value={q} total={($rows.data ?? []).length} shown={mostrados}
           placeholder="buscar por número, peça ou cliente…" />
```

E passar `searchText={q}` e `searchExtra={(r) => (r as Quote).notes ?? ""}` para a `Table`.

- [ ] **Step 2: Converter as demais**

Mesmo padrão para `clients`, `spools`, `materials` e `library`. Campos buscáveis: nome e contato em clientes; material, cor e fabricante em estoque; nome e tipo em materiais; nome e autor na biblioteca.

- [ ] **Step 3: Verificar**

```bash
cd frontend && npm run check && npm run build
```

Abrir cada tela e conferir: busca filtra, contador bate, ordenação cicla nos três estados, limpar restaura.

- [ ] **Step 4: Commit**

Um commit por página.

---

### Task 7: Responsivo

**Files:**
- Modify: `frontend/src/app.css`
- Modify: `frontend/src/lib/components/Table.svelte`
- Modify: `frontend/src/routes/+layout.svelte`
- Test: `tests/e2e/mobile.spec.ts`

**Interfaces:**
- Consumes: `Table` (Task 5).
- Produces: prop `stackOnMobile?: boolean` (default `true`) na `Table`.

- [ ] **Step 1: Escrever o teste E2E que falha**

Create `tests/e2e/mobile.spec.ts`:

```ts
import { test, expect } from "@playwright/test";

// Viewport de telefone comum. A conferência de bancada acontece aqui.
test.use({ viewport: { width: 390, height: 844 } });

async function login(page) {
  await page.goto("/login");
  await page.fill('input[type="email"]', "t@t.com");
  await page.fill('input[type="password"]', "pw");
  await page.click('button[type="submit"]');
  await page.waitForURL("/");
}

for (const rota of ["/quotes", "/accounting", "/spools", "/clients"]) {
  test(`${rota} não rola horizontalmente em 390px`, async ({ page }) => {
    await login(page);
    await page.goto(rota);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(
      () => document.body.scrollWidth - document.body.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
  });
}
```

Conferir antes as credenciais de seed e o seletor do login em `tests/e2e/` — usar exatamente o que o spec existente usa, em vez do esboço acima.

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
make up && make seed && make e2e
```

Expected: FAIL nas rotas com tabela larga.

- [ ] **Step 3: Documentar a escala de breakpoints**

No topo de `frontend/src/app.css`, depois do `@import`:

```css
/* Escala de breakpoints do app. Media query não aceita var(), então os
   literais abaixo são a referência única — não inventar um quarto valor
   numa página qualquer.
     560px  telefone em pé
     700px  limite do modo card das tabelas
     880px  colapso da sidebar (já em uso)
    1180px  largura máxima de main  */
```

- [ ] **Step 4: Modo card na `Table`**

No markup da `Table`, adicionar uma segunda renderização, escondida por CSS acima do breakpoint:

```svelte
<div class="cards" class:enabled={stackOnMobile}>
  {#each visible as row (rowKey(row))}
    <article class="card">
      {#each columns as c}
        <div class="card-row">
          <span class="card-label mono">{c.label}</span>
          <span class="card-value" class:mono={c.mono}>{display(c, row)}</span>
        </div>
      {/each}
      {#if $$slots.actions}
        <div class="card-actions"><slot name="actions" {row} /></div>
      {/if}
    </article>
  {/each}
  {#if visible.length === 0}
    <div class="empty">{searchText ? "Nada encontrado para a busca" : empty}</div>
  {/if}
</div>
```

```css
  .cards { display: none; }
  @media (max-width: 700px) {
    .cards.enabled { display: grid; gap: 0.75rem; }
    .cards.enabled + .table-wrap,
    .table-wrap:has(+ .cards.enabled) { display: none; }
  }
```

Cuidado: `:has()` tem suporte amplo, mas a combinação acima depende da ordem dos elementos. Mais seguro é envolver os dois num wrapper e alternar com uma classe no wrapper — decidir na implementação, testando nos dois tamanhos.

Toda coluna aparece no card. Nada é omitido por largura — esconder informação no celular seria trocar um problema por outro.

- [ ] **Step 5: Alvos de toque**

Em `app.css`, garantir `min-height: 44px` e área clicável adequada em `.chip`, `.tiny`, e nos checkboxes de linha. Aumentar padding e área, **não** o tamanho da fonte — o desenho tipográfico do app depende das escalas atuais.

- [ ] **Step 6: Gutters**

Conferir que nenhuma página zera o respiro lateral:

```bash
grep -rn "padding: 0\|padding:0" frontend/src/routes/*/+page.svelte | grep -v "padding: 0\." | head
```

Onde uma página redefine `padding` com shorthand, trocar por `padding-block` para preservar os lados.

- [ ] **Step 7: Rodar o E2E e o resto**

```bash
make e2e
cd frontend && npm test && npm run check && npm run build
cd .. && make test 2>&1 | tail -5 && make lint
```

Expected: tudo verde, incluindo os 4 testes de 390px.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app.css frontend/src/lib/components/Table.svelte \
        frontend/src/routes/+layout.svelte tests/e2e/mobile.spec.ts
git commit -m "feat(ui): modo card nas tabelas abaixo de 700px + alvos de toque

Todas as colunas aparecem no card — nada é omitido por largura.
E2E em 390px garante que nenhuma lista rola horizontalmente.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Critério de pronto da Spec 1

- [ ] `make test`, `make lint`, `make e2e` verdes.
- [ ] `cd frontend && npm test` verde.
- [ ] `alembic upgrade head` e `alembic downgrade -1` rodam limpos num banco com dados.
- [ ] Backfill verificado: `seq` de 1 a N em ordem cronológica, sem buracos.
- [ ] Nenhuma tela exibe UUID de orçamento.
- [ ] Orçamentos, Clientes, Estoque, Materiais e Biblioteca têm busca e ordenação.
- [ ] Em 390px, nenhuma das rotas testadas rola horizontalmente.
