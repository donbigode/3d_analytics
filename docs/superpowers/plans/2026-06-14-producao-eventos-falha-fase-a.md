# Produção em fila + eventos de falha — Fase A — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tornar "Produzir" um fluxo de fila (status `em_producao`) que deduz material na entrada, com desfecho explícito **Concluir**/**Falhar** na aba Capacidade, gravando `production_events` e expondo taxa de falha agregada em Insights.

**Architecture:** Backend FastAPI + SQLAlchemy async; novos estados em `QuoteStatus` (StrEnum/String, sem enum no banco); nova tabela `production_events` (Alembic, com colunas `embedding`/`llm_tags` já criadas mas nulas para a Fase B). Transições de quote ganham `complete`/`fail` e o `produce` passa a parar em `em_producao`. Frontend SvelteKit: Capacidade com fila ativa + ações; aba Insights com tabela de taxa de falha (puro SQL).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Postgres 16 (pgvector já instalado), pytest + httpx; SvelteKit (Svelte 5) + svelte-check. Testes rodam em container: `docker compose run --rm api pytest ...`.

**Referência do spec:** `docs/superpowers/specs/2026-06-14-producao-eventos-falha-design.md`

---

## Arquivos (mapa)

- `backend/core/models.py` — adicionar `QuoteStatus.EM_PRODUCAO`, `QuoteStatus.FALHOU`; novos enums `ProductionOutcome`.
- `backend/infra/db/models/production_event.py` — **criar** modelo `ProductionEvent`.
- `backend/infra/db/models/__init__.py` — exportar `ProductionEvent`.
- `migrations/versions/0023_production_events.py` — **criar** tabela + extensão vector + índice.
- `backend/api/schemas/quotes.py` — `CompleteRequest`, `FailRequest`; expor novos estados.
- `backend/api/routes/quotes.py` — ajustar `t_produce` (→ `em_producao`, origem `aprovado`/`draft`/`falhou`); adicionar `t_complete`, `t_fail`; helper de snapshot de contexto + grams do ciclo.
- `backend/api/routes/capacity.py` — endpoint `/capacity/in-production` (fila FIFO de `em_producao`).
- `backend/api/schemas/capacity.py` — `InProductionOut`.
- `backend/api/routes/insights.py` — agregação de taxa de falha (`/insights/failure-rates`).
- `backend/api/schemas/insights.py` (ou inline) — shape da resposta.
- `frontend/src/lib/types.ts` — `QuoteStatus` += `em_producao`/`falhou`; tipos novos.
- `frontend/src/routes/capacity/+page.svelte` — seção "Em produção" com Concluir/Falhar.
- `frontend/src/routes/quotes/[id]/+page.svelte` — wiring de complete/fail/re-produzir + timeline.
- `frontend/src/routes/insights/+page.svelte` — tabela de taxa de falha.
- Testes: `backend/tests/api/test_production_flow.py`, `test_capacity_endpoints.py`, `test_insights*.py`.

---

## Task 1: Novos estados e enum de desfecho

**Files:**
- Modify: `backend/core/models.py`

- [ ] **Step 1: Adicionar os valores ao enum**

Em `backend/core/models.py`, na classe `QuoteStatus` (StrEnum), adicionar após `APROVADO`:

```python
class QuoteStatus(StrEnum):
    DRAFT = "draft"
    ORCADO = "orcado"
    APROVADO = "aprovado"
    EM_PRODUCAO = "em_producao"
    PRODUZIDO = "produzido"
    ENTREGUE = "entregue"
    FALHOU = "falhou"
    CANCELADO = "cancelado"


class ProductionOutcome(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
```

(Adicionar `from enum import StrEnum` se ainda não estiver importado — provavelmente já está.)

- [ ] **Step 2: Sanidade de import**

Run: `docker compose run --rm api python -c "from backend.core.models import QuoteStatus, ProductionOutcome; print(QuoteStatus.EM_PRODUCAO, ProductionOutcome.FAILURE)"`
Expected: imprime `em_producao failure` sem erro.

- [ ] **Step 3: Commit**

```bash
git add backend/core/models.py
git commit -m "feat(models): estados em_producao/falhou + ProductionOutcome"
```

---

## Task 2: Modelo `ProductionEvent` + migração

**Files:**
- Create: `backend/infra/db/models/production_event.py`
- Modify: `backend/infra/db/models/__init__.py`
- Create: `migrations/versions/0023_production_events.py`

- [ ] **Step 1: Escrever o teste que falha**

Em `backend/tests/api/test_production_flow.py` (novo arquivo):

```python
import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_production_event_table_exists(auth_client):
    # Smoke: a tabela existe e aceita insert via ORM importável.
    from backend.infra.db.models import ProductionEvent
    assert ProductionEvent.__tablename__ == "production_events"
    cols = set(ProductionEvent.__table__.columns.keys())
    assert {"id", "quote_id", "kind", "outcome", "attempts",
            "failure_description", "context", "grams_wasted",
            "embedding", "llm_tags", "created_at"} <= cols
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_flow.py::test_production_event_table_exists -q`
Expected: FAIL com `ImportError: cannot import name 'ProductionEvent'`.

- [ ] **Step 3: Criar o modelo**

`backend/infra/db/models/production_event.py`:

```python
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Integer, Numeric, Text, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base

EMBEDDING_DIM = 384


class ProductionEvent(Base):
    __tablename__ = "production_events"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failure_description: Mapped[str | None] = mapped_column(Text)
    context: Mapped[list | dict | None] = mapped_column(JSONB)
    grams_wasted: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    llm_tags: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 4: Exportar no `__init__`**

Em `backend/infra/db/models/__init__.py`, seguir o padrão existente e adicionar:

```python
from backend.infra.db.models.production_event import ProductionEvent  # noqa: F401
```
(e incluir `"ProductionEvent"` em `__all__` se o arquivo tiver um.)

- [ ] **Step 5: Criar a migração**

`migrations/versions/0023_production_events.py` (segue o padrão de `0006_llm_radar` para o vetor):

```python
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "0023_production_events"
down_revision: Union[str, Sequence[str], None] = "0022_spool_color_mfr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "production_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("quote_id", UUID(as_uuid=True),
                  sa.ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="1"),
        sa.Column("failure_description", sa.Text),
        sa.Column("context", JSONB),
        sa.Column("grams_wasted", sa.Numeric(10, 2)),
        sa.Column("llm_tags", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )
    op.execute("ALTER TABLE production_events ADD COLUMN embedding vector(384)")
    op.execute(
        "CREATE INDEX production_events_embedding_idx ON production_events "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
    op.create_index("ix_production_events_quote_id", "production_events", ["quote_id"])
    op.create_index("ix_production_events_outcome", "production_events", ["outcome"])


def downgrade() -> None:
    op.drop_table("production_events")
```

- [ ] **Step 6: Rodar o teste (rebuild do DB de teste aplica a migração)**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_flow.py::test_production_event_table_exists -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/infra/db/models/production_event.py backend/infra/db/models/__init__.py migrations/versions/0023_production_events.py backend/tests/api/test_production_flow.py
git commit -m "feat(db): tabela production_events + migração 0023"
```

---

## Task 3: `produce` para de em `em_producao` (e aceita re-produzir de `falhou`)

**Files:**
- Modify: `backend/api/routes/quotes.py` (função `t_produce`)
- Test: `backend/tests/api/test_production_flow.py`

- [ ] **Step 1: Escrever o teste que falha**

Adicionar em `test_production_flow.py` (reusar helpers de `test_quotes_lifecycle.py`; copiar `GCODE_SAMPLE` e `_seed_material` ou importar):

```python
GCODE = b";TIME:3600\n;Filament used:5.0m\n;Material Type:PLA\n"


async def _seed_material(c):
    await c.post("/materials", json={"material_type": "PLA", "name": "PLA",
        "density_g_cm3": "1.24", "price_per_kg_ref": "100", "failure_rate_pct": "0"})


async def _spool(c):
    r = await c.post("/spools", json={"material_type": "PLA",
        "purchased_at": "2026-06-01T00:00:00Z", "purchased_price": "100",
        "initial_grams": "1000", "remaining_grams": "1000"})
    return r.json()["id"]


async def _approved_commercial(c):
    r = await c.post("/quotes", json={"kind": "commercial"}); qid = r.json()["id"]
    await c.post(f"/quotes/{qid}/items", files={"file": ("x.gcode", GCODE, "application/octet-stream")},
                 data={"name": "X", "quantity": "1"})
    await c.post(f"/quotes/{qid}/transitions/finalize")
    await c.post(f"/quotes/{qid}/transitions/approve")
    item_id = (await c.get(f"/quotes/{qid}")).json()["items"][0]["id"]
    return qid, item_id


@pytest.mark.asyncio
async def test_produce_enters_em_producao(auth_client):
    await _seed_material(auth_client)
    sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial(auth_client)
    r = await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "em_producao"
    s = (await auth_client.get(f"/spools/{sid}")).json()
    from decimal import Decimal
    assert Decimal(s["remaining_grams"]) < Decimal("1000")  # material já deduzido
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_flow.py::test_produce_enters_em_producao -q`
Expected: FAIL — status volta `produzido`, não `em_producao`.

- [ ] **Step 3: Ajustar `t_produce`**

Em `backend/api/routes/quotes.py`, na função `t_produce`: trocar o bloco de validação de origem e o status final. A origem comercial passa a aceitar `APROVADO` **ou** `FALHOU`; a pessoal `DRAFT` **ou** `FALHOU`. No fim, `q.status = QuoteStatus.EM_PRODUCAO` (remover `q.produced_at = _now()` daqui — vai para o `complete`).

```python
    if q.kind == QuoteKind.COMMERCIAL:
        if q.status not in (QuoteStatus.APROVADO, QuoteStatus.FALHOU):
            raise HTTPException(409, "quote must be aprovado (ou falhou) before produce")
    elif q.kind == QuoteKind.PERSONAL:
        if q.status not in (QuoteStatus.DRAFT, QuoteStatus.FALHOU):
            raise HTTPException(409, "personal quote must be draft (ou falhou) to produce")
        await _assert_materials_resolved(session, q)
        if q.finalized_at is None:
            q.finalized_at = _now()
    else:
        raise HTTPException(400, "unsupported quote kind for produce")
    # ... loop de consumo inalterado (com a guarda de grams<=0) ...
    q.status = QuoteStatus.EM_PRODUCAO
    await session.commit()
    return await _quote_out(session, q)
```

- [ ] **Step 4: Rodar e ver passar (e suíte de lifecycle não quebrar onde produce era terminal)**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_flow.py::test_produce_enters_em_producao backend/tests/api/test_quotes_lifecycle.py backend/tests/api/test_quotes_personal.py -q`
Expected: o novo PASS. Os testes antigos que esperavam `produzido` direto do produce vão FALHAR — eles serão atualizados no Task 4/5 (o desfecho agora é `complete`). Se algum teste antigo falhar SÓ por causa do novo passo, anotar para ajustar no Task 5, Step "atualizar testes legados".

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/quotes.py backend/tests/api/test_production_flow.py
git commit -m "feat(quotes): produce para em_producao e aceita re-produzir de falhou"
```

---

## Task 4: Transição `complete` (sucesso) + evento

**Files:**
- Modify: `backend/api/schemas/quotes.py`, `backend/api/routes/quotes.py`
- Test: `backend/tests/api/test_production_flow.py`

- [ ] **Step 1: Teste que falha**

```python
@pytest.mark.asyncio
async def test_complete_marks_produzido_and_logs_success(auth_client):
    await _seed_material(auth_client); sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    r = await auth_client.post(f"/quotes/{qid}/transitions/complete", json={"attempts": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "produzido"
    assert body["produced_at"] is not None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_flow.py::test_complete_marks_produzido_and_logs_success -q`
Expected: FAIL — rota `complete` não existe (404/405).

- [ ] **Step 3: Schema + helper de contexto/grams**

Em `backend/api/schemas/quotes.py`:

```python
class CompleteRequest(BaseModel):
    attempts: int = 1


class FailRequest(BaseModel):
    failure_description: str
    attempts: int = 1
```

Em `backend/api/routes/quotes.py`, importar `CompleteRequest`, `FailRequest`, `ProductionEvent`, `ProductionOutcome` e adicionar helpers + a rota:

```python
async def _cycle_context_and_grams(session, q):
    """Snapshot por peça + soma de grams consumidos no ciclo corrente."""
    items = (await session.execute(
        select(QuoteItem).where(QuoteItem.quote_id == q.id))).scalars().all()
    ctx = []
    grams = Decimal("0")
    for it in items:
        meta = it.gcode_meta or {}
        cons = (await session.execute(
            select(MaterialConsumption).where(MaterialConsumption.quote_item_id == it.id)
        )).scalars().all()
        sp = None
        if cons:
            sp = await session.get(Spool, cons[-1].spool_id)
            grams += sum((c.grams_used or Decimal("0")) for c in cons)
        ctx.append({
            "name": it.name,
            "material_type": (sp.material_type if sp else meta.get("material")),
            "color": (sp.color if sp else None),
            "manufacturer": (sp.manufacturer if sp else None),
            "filament_m": meta.get("filament_m"),
            "time_s": meta.get("time_s"),
            "is_multi_color": bool(getattr(it, "is_multi_color", False)),
            "machine": meta.get("machine"),
            "model_source_url": getattr(it, "model_source_url", None),
        })
    return ctx, grams


@router.post("/{quote_id}/transitions/complete", response_model=QuoteOut)
async def t_complete(quote_id: UUID, payload: CompleteRequest,
                     _: User = Depends(require_user),
                     session: AsyncSession = Depends(db_session)):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.EM_PRODUCAO:
        raise HTTPException(409, "quote must be em_producao to complete")
    ctx, grams = await _cycle_context_and_grams(session, q)
    session.add(ProductionEvent(
        quote_id=q.id, kind=q.kind, outcome=ProductionOutcome.SUCCESS,
        attempts=max(1, payload.attempts), context=ctx, grams_wasted=None,
    ))
    q.status = QuoteStatus.PRODUZIDO
    q.produced_at = _now()
    await session.commit()
    return await _quote_out(session, q)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_flow.py::test_complete_marks_produzido_and_logs_success -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/schemas/quotes.py backend/api/routes/quotes.py backend/tests/api/test_production_flow.py
git commit -m "feat(quotes): transição complete -> produzido + evento success"
```

---

## Task 5: Transição `fail` (falhou) + evento + atualizar testes legados

**Files:**
- Modify: `backend/api/routes/quotes.py`
- Test: `backend/tests/api/test_production_flow.py`; ajustar `test_quotes_lifecycle.py`, `test_quotes_personal.py`, `test_capacity_endpoints.py`

- [ ] **Step 1: Teste que falha**

```python
from decimal import Decimal

@pytest.mark.asyncio
async def test_fail_marks_falhou_and_logs_failure(auth_client):
    await _seed_material(auth_client); sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    r = await auth_client.post(f"/quotes/{qid}/transitions/fail",
        json={"failure_description": "descolou da mesa", "attempts": 3})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "falhou"
    # re-produzir: de falhou volta a em_producao (deduz de novo)
    r2 = await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "em_producao"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_flow.py::test_fail_marks_falhou_and_logs_failure -q`
Expected: FAIL — rota `fail` não existe.

- [ ] **Step 3: Implementar `t_fail`**

```python
@router.post("/{quote_id}/transitions/fail", response_model=QuoteOut)
async def t_fail(quote_id: UUID, payload: FailRequest,
                 _: User = Depends(require_user),
                 session: AsyncSession = Depends(db_session)):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.status != QuoteStatus.EM_PRODUCAO:
        raise HTTPException(409, "quote must be em_producao to fail")
    desc = (payload.failure_description or "").strip()
    if not desc:
        raise HTTPException(400, "failure_description is required")
    ctx, grams = await _cycle_context_and_grams(session, q)
    session.add(ProductionEvent(
        quote_id=q.id, kind=q.kind, outcome=ProductionOutcome.FAILURE,
        attempts=max(1, payload.attempts), failure_description=desc,
        context=ctx, grams_wasted=grams,
    ))
    q.status = QuoteStatus.FALHOU
    await session.commit()
    return await _quote_out(session, q)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_flow.py -q`
Expected: PASS (todos do arquivo).

- [ ] **Step 5: Atualizar testes legados que assumiam produce→produzido direto**

Em `test_quotes_lifecycle.py` (`test_produce_consumes_spool`, `test_commercial_can_deliver_after_produce`) e `test_quotes_personal.py` (`test_personal_produce_consumes_spool`, `test_personal_workflow_skips_aprovado`): após o POST `produce`, inserir o passo de conclusão antes de checar `produzido`/`deliver`:

```python
    await auth_client.post(f"/quotes/{qid}/transitions/complete", json={"attempts": 1})
```
E onde o teste afirmava `r.json()["status"] == "produzido"` logo após produce, mover essa asserção para depois do `complete`. Em `test_capacity_endpoints.py`, se algum helper produz e espera o quote fora da fila de aprovados, ajustar para o novo fluxo (produce → em_producao).

- [ ] **Step 6: Rodar a suíte inteira**

Run: `docker compose run --rm api pytest -q`
Expected: tudo PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/api/routes/quotes.py backend/tests/api/
git commit -m "feat(quotes): transição fail -> falhou + evento; ajusta testes do novo fluxo"
```

---

## Task 6: Capacidade — fila "em produção" (FIFO)

**Files:**
- Modify: `backend/api/routes/capacity.py`, `backend/api/schemas/capacity.py`
- Test: `backend/tests/api/test_capacity_endpoints.py`

- [ ] **Step 1: Teste que falha**

```python
@pytest.mark.asyncio
async def test_in_production_queue_lists_em_producao(auth_client):
    # usa helpers locais do arquivo de capacidade; cria, aprova, produz 1 quote
    await _seed_material(auth_client); sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    r = await auth_client.get("/capacity/in-production")
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    assert any(j["quote_id"] == qid for j in jobs)
```

(Se os helpers `_seed_material/_spool/_approved_commercial` não existirem nesse arquivo, importar de `test_production_flow` ou duplicar — manter o teste autocontido.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_capacity_endpoints.py::test_in_production_queue_lists_em_producao -q`
Expected: FAIL — rota não existe.

- [ ] **Step 3: Schema**

Em `backend/api/schemas/capacity.py`:

```python
class InProductionJob(BaseModel):
    quote_id: str
    name: str
    kind: str
    hours: Decimal
    entered_at: datetime | None


class InProductionOut(BaseModel):
    jobs: list[InProductionJob]
```

- [ ] **Step 4: Endpoint**

Em `backend/api/routes/capacity.py` (reusar `_quote_hours`):

```python
from backend.api.schemas.capacity import InProductionOut

@router.get("/in-production", response_model=InProductionOut)
async def in_production(_: User = Depends(require_user),
                       session: AsyncSession = Depends(db_session)):
    res = await session.execute(
        select(Quote).where(Quote.status == QuoteStatus.EM_PRODUCAO)
        .order_by(Quote.produced_at.asc().nulls_last(), Quote.created_at.asc())
    )
    jobs = []
    for q in res.scalars():
        items = (await session.execute(
            select(QuoteItem).where(QuoteItem.quote_id == q.id))).scalars().all()
        jobs.append({
            "quote_id": str(q.id),
            "name": (items[0].name if items else str(q.id)[:8]),
            "kind": q.kind,
            "hours": _quote_hours(items),
            "entered_at": q.produced_at,
        })
    return {"jobs": jobs}
```

- [ ] **Step 5: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_capacity_endpoints.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routes/capacity.py backend/api/schemas/capacity.py backend/tests/api/test_capacity_endpoints.py
git commit -m "feat(capacity): fila em-produção (FIFO) read-only"
```

---

## Task 7: Insights — taxa de falha agregada (SQL, sem IA)

**Files:**
- Modify: `backend/api/routes/insights.py`
- Test: `backend/tests/api/test_insights_failure_rates.py` (novo)

- [ ] **Step 1: Teste que falha**

`backend/tests/api/test_insights_failure_rates.py`:

```python
import pytest
# reusar helpers de test_production_flow via import
from backend.tests.api.test_production_flow import (
    _seed_material, _spool, _approved_commercial)


@pytest.mark.asyncio
async def test_failure_rates_by_material(auth_client):
    await _seed_material(auth_client); sid = await _spool(auth_client)
    # 1 falha
    qid, item_id = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    await auth_client.post(f"/quotes/{qid}/transitions/fail",
        json={"failure_description": "warping", "attempts": 1})
    # 1 sucesso
    qid2, item2 = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid2}/transitions/produce",
        json={"consumption": [{"quote_item_id": item2, "spool_id": sid}]})
    await auth_client.post(f"/quotes/{qid2}/transitions/complete", json={"attempts": 1})

    r = await auth_client.get("/insights/failure-rates")
    assert r.status_code == 200, r.text
    rows = r.json()["by_material"]
    pla = next(x for x in rows if x["material_type"] == "PLA")
    assert pla["failures"] == 1
    assert pla["total"] == 2
    assert 0.49 <= float(pla["failure_rate"]) <= 0.51
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_insights_failure_rates.py -q`
Expected: FAIL — rota não existe.

- [ ] **Step 3: Implementar agregação**

Em `backend/api/routes/insights.py` adicionar endpoint que lê `production_events` e agrega por `material_type` extraído do `context` (cada evento pode ter várias peças; conta o evento por material distinto presente). Implementação em Python (JSONB cross-engine simples):

```python
from backend.infra.db.models import ProductionEvent

@router.get("/failure-rates")
async def failure_rates(_: User = Depends(require_user),
                        session: AsyncSession = Depends(db_session)):
    evs = (await session.execute(select(ProductionEvent))).scalars().all()
    agg: dict[str, dict[str, int]] = {}
    for e in evs:
        mats = set()
        for piece in (e.context or []):
            mt = (piece or {}).get("material_type")
            if mt:
                mats.add(mt)
        for mt in (mats or {None}):
            key = mt or "—"
            a = agg.setdefault(key, {"failures": 0, "total": 0})
            a["total"] += 1
            if e.outcome == "failure":
                a["failures"] += 1
    by_material = [
        {"material_type": k, "failures": v["failures"], "total": v["total"],
         "failure_rate": (v["failures"] / v["total"]) if v["total"] else 0.0}
        for k, v in sorted(agg.items())
    ]
    return {"by_material": by_material}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_insights_failure_rates.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/insights.py backend/tests/api/test_insights_failure_rates.py
git commit -m "feat(insights): taxa de falha agregada por material (SQL)"
```

---

## Task 8: Frontend — Capacidade (ações), orçamento (wiring), Insights (tabela)

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/routes/capacity/+page.svelte`, `frontend/src/routes/quotes/[id]/+page.svelte`, `frontend/src/routes/insights/+page.svelte`

- [ ] **Step 1: Tipos**

Em `frontend/src/lib/types.ts`: em `QuoteStatus` adicionar `| "em_producao"` e `| "falhou"`. Adicionar:

```ts
export type InProductionJob = { quote_id: string; name: string; kind: string; hours: number | string; entered_at: string | null };
export type InProductionOut = { jobs: InProductionJob[] };
export type FailureRateRow = { material_type: string; failures: number; total: number; failure_rate: number };
```

- [ ] **Step 2: Capacidade — seção "Em produção" com ações**

Em `frontend/src/routes/capacity/+page.svelte`: carregar `api<InProductionOut>("/capacity/in-production")` no load. Renderizar uma seção acima do forecast com os jobs; cada um com botões **Concluir** e **Falhar**. Concluir: `POST /quotes/{id}/transitions/complete {attempts}` (prompt simples de tentativas, default 1). Falhar: abre mini-modal com textarea `failure_description` + número `attempts` → `POST /quotes/{id}/transitions/fail`. Após cada ação, recarregar a lista. Seguir o padrão visual existente da página (cards/listas) e a skill `frontend-design` para o estilo.

- [ ] **Step 3: Orçamento — timeline e re-produzir**

Em `frontend/src/routes/quotes/[id]/+page.svelte`: no mapa de rótulos de status, adicionar `em_producao: "Em produção"` e `falhou: "Falhou"`. Para `status === "em_producao"` mostrar atalho "Ver na Capacidade" (`href="/capacity"`). Para `status === "falhou"` mostrar botão **Re-produzir** que chama `openProduce()` (o produce já aceita origem `falhou`). A função `transition()` não precisa de complete/fail aqui (essas ações vivem na Capacidade).

- [ ] **Step 4: Insights — tabela de taxa de falha**

Em `frontend/src/routes/insights/+page.svelte`: carregar `api<{by_material: FailureRateRow[]}>("/insights/failure-rates")` e renderizar uma seção "Atenção na produção" com tabela Material | Falhas | Total | Taxa (%). Sem IA nesta fase.

- [ ] **Step 5: Verificar**

Run: `cd frontend && npm run check`
Expected: nenhum erro NOVO (os 5 pré-existentes de `library`/`low_spool_threshold_g` podem permanecer). Conferir que os arquivos tocados não introduzem erros de tipo.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat(ui): capacidade com fila em-produção (concluir/falhar), re-produzir e taxa de falha em insights"
```

---

## Self-review (cobertura do spec)

- Estados `em_producao`/`falhou` → Task 1. ✓
- Dedução no produce + origem aprovado/draft/falhou → Task 3. ✓
- `complete`/`fail` + `production_events` (contexto por peça, grams_wasted, attempts) → Tasks 4–5. ✓
- Capacidade fila FIFO em produção → Task 6 (forecast de aprovados permanece). ✓
- Insights taxa de falha (SQL) → Task 7. ✓
- UI (capacidade ações, re-produzir, insights) → Task 8. ✓
- `embedding`/`llm_tags` criados nulos (Fase B) → Task 2 (colunas) — pipeline LLM e sugestões ficam para o **plano da Fase B**.

Fora de escopo desta fase (Fase B, plano separado): geração de embeddings, parsing LLM (`llm_tags`), busca vetorial e sugestões sob demanda na aba Insights.
