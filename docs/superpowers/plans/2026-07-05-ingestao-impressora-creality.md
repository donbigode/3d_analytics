# Ingestão de jobs da impressora (Creality/Moonraker) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Receber jobs finalizados da Creality K1 (via agente local que lê o Moonraker) num endpoint de ingestão, guardá-los num inbox próprio e permitir vinculá-los a um orçamento existente, produzindo com as gramas/tempo reais e baixando o spool escolhido.

**Architecture:** Um endpoint `POST /ingest/print-jobs` autenticado por token de agente insere (idempotente) em `printer_jobs`. Endpoints de gestão (`/printer-jobs`) listam/descartam/linkam. O link reusa a máquina de `produce` já existente (extraída pra um helper `apply_production`), convertendo `filament_used_mm` → gramas com a densidade do material do item.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2, Postgres. Testes com pytest-asyncio rodando via `docker compose run --rm api`.

## Global Constraints

- Testes/lint/migração rodam via `docker compose run --rm api <cmd>` (nunca localmente).
- Migração Alembic: nova revisão `0030_printer_jobs`, `down_revision = "0029_people_quote_people"`.
- Enums são `StrEnum` em `backend/core/models.py`.
- Modelos usam `PG_UUID(as_uuid=True)`, `Numeric`, `DateTime(timezone=True)`; toda tabela nova entra em `backend/infra/db/models/__init__.py` (import + `__all__`) e na tupla de limpeza de `backend/tests/api/conftest.py`.
- O root conftest aplica `alembic upgrade head` no DB de teste automaticamente — basta a migração existir.
- Commits frequentes, mensagem em pt-BR, terminando com:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

**Criar:**
- `backend/infra/db/models/printer_job.py` — modelo `PrinterJob`.
- `backend/api/routes/printer.py` — `ingest_router` (`/ingest`) + `router` (`/printer-jobs`).
- `backend/api/schemas/printer.py` — schemas de ingestão e link.
- `migrations/versions/0030_printer_jobs.py` — tabela `printer_jobs`.
- `backend/tests/api/test_printer_ingest.py` — testes de ingestão.
- `backend/tests/api/test_printer_link.py` — testes de link.
- `frontend/src/routes/printer-jobs/+page.svelte` — aba "Impressora".

**Modificar:**
- `backend/core/models.py` — enum `PrinterJobStatus`.
- `backend/infra/db/models/__init__.py` — export `PrinterJob`.
- `backend/tests/api/conftest.py` — import + limpeza de `PrinterJob`.
- `backend/settings.py` — `agent_ingest_token`.
- `backend/api/routes/quotes.py` — extrair `apply_production`; `t_produce` passa a chamá-lo.
- `backend/app.py` — registrar os dois routers.
- `frontend/src/lib/types.ts` — tipo `PrinterJobItem`.
- `frontend/src/routes/+layout.svelte` — link de navegação pra nova página.

---

## Task 1: Modelo `PrinterJob` + enum + migração

**Files:**
- Modify: `backend/core/models.py`
- Create: `backend/infra/db/models/printer_job.py`
- Modify: `backend/infra/db/models/__init__.py`
- Modify: `backend/tests/api/conftest.py`
- Create: `migrations/versions/0030_printer_jobs.py`
- Test: `backend/tests/api/test_printer_ingest.py` (só o teste de round-trip do modelo nesta task)

**Interfaces:**
- Produces: `PrinterJob` (SQLAlchemy model, tabela `printer_jobs`), `PrinterJobStatus` (StrEnum: `PENDING="pending"`, `LINKED="linked"`, `DISCARDED="discarded"`).

- [ ] **Step 1: Adicionar o enum**

Em `backend/core/models.py`, após a classe `WatcherInboxStatus`:

```python
class PrinterJobStatus(StrEnum):
    PENDING = "pending"
    LINKED = "linked"
    DISCARDED = "discarded"
```

- [ ] **Step 2: Criar o modelo**

Criar `backend/infra/db/models/printer_job.py`:

```python
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import String, Numeric, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base
from backend.core.models import PrinterJobStatus


class PrinterJob(Base):
    __tablename__ = "printer_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    machine: Mapped[str] = mapped_column(String(120), nullable=False)
    job_uid: Mapped[str] = mapped_column(String(120), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    filament_used_mm: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    time_s: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    grams: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    inbox_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PrinterJobStatus.PENDING
    )
    quote_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 3: Registrar no `__init__`**

Em `backend/infra/db/models/__init__.py`, adicionar o import (ordem alfabética junto aos outros) e incluir no `__all__`:

```python
from backend.infra.db.models.printer_job import PrinterJob
```

E em `__all__`, adicionar `"PrinterJob"` (junto de `"ProductionEvent"`).

- [ ] **Step 4: Registrar na limpeza dos testes**

Em `backend/tests/api/conftest.py`, adicionar `PrinterJob` ao import de `backend.infra.db.models` e à tupla de `delete()` — **antes** de `Quote.__table__` (tem FK para quotes):

```python
                    PrinterJob.__table__,
```

(colocar logo após `MaterialConsumption.__table__,`)

- [ ] **Step 5: Criar a migração**

Criar `migrations/versions/0030_printer_jobs.py`:

```python
"""printer_jobs (ingestão de jobs da impressora)

Revision ID: 0030_printer_jobs
Revises: 0029_people_quote_people
Create Date: 2026-07-05 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision: str = "0030_printer_jobs"
down_revision: Union[str, Sequence[str], None] = "0029_people_quote_people"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "printer_jobs",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("machine", sa.String(120), nullable=False),
        sa.Column("job_uid", sa.String(120), nullable=False),
        sa.Column("filename", sa.String(500)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("filament_used_mm", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("time_s", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("grams", sa.Numeric(10, 2)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("raw", JSONB, nullable=False, server_default="{}"),
        sa.Column("inbox_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("quote_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("quotes.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_printer_jobs_machine_job", "printer_jobs", ["machine", "job_uid"]
    )


def downgrade() -> None:
    op.drop_table("printer_jobs")
```

- [ ] **Step 6: Escrever o teste de round-trip**

Criar `backend/tests/api/test_printer_ingest.py`:

```python
import pytest

from backend.infra.db import session as session_module
from backend.infra.db.models import PrinterJob
from backend.core.models import PrinterJobStatus


@pytest.mark.asyncio
async def test_printer_job_roundtrip():
    async with session_module.SessionFactory() as s:
        job = PrinterJob(
            machine="K1-oficina",
            job_uid="42",
            filename="peca.gcode",
            status="completed",
            filament_used_mm=3000,
            time_s=5000,
            raw={"foo": "bar"},
        )
        s.add(job)
        await s.commit()
        await s.refresh(job)
        assert job.inbox_status == PrinterJobStatus.PENDING
        assert job.filament_used_mm == 3000
```

- [ ] **Step 7: Rodar migração + teste**

Run:
```bash
docker compose run --rm api alembic upgrade head
docker compose run --rm api pytest backend/tests/api/test_printer_ingest.py::test_printer_job_roundtrip -v
```
Expected: migração OK; teste PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/core/models.py backend/infra/db/models/printer_job.py \
  backend/infra/db/models/__init__.py backend/tests/api/conftest.py \
  migrations/versions/0030_printer_jobs.py backend/tests/api/test_printer_ingest.py
git commit -m "feat(printer): modelo PrinterJob + migração 0030

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Endpoint de ingestão `POST /ingest/print-jobs`

**Files:**
- Modify: `backend/settings.py`
- Create: `backend/api/schemas/printer.py`
- Create: `backend/api/routes/printer.py`
- Modify: `backend/app.py`
- Test: `backend/tests/api/test_printer_ingest.py`

**Interfaces:**
- Consumes: `PrinterJob`, `PrinterJobStatus` (Task 1).
- Produces: `ingest_router` (APIRouter, monta em `/ingest`), rota `POST /ingest/print-jobs`. Schema `PrintJobIn` com campos `machine, job_uid, filename, status, filament_used_mm, print_duration_s, started_at, finished_at, raw`.

- [ ] **Step 1: Adicionar o token nas settings**

Em `backend/settings.py`, dentro de `AppSettings`, após `watch_dir`:

```python
    agent_ingest_token: str | None = None
```

- [ ] **Step 2: Escrever os schemas**

Criar `backend/api/schemas/printer.py`:

```python
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PrintJobIn(BaseModel):
    machine: str
    job_uid: str
    filename: str | None = None
    status: str  # completed | cancelled | error
    filament_used_mm: Decimal = Decimal("0")
    print_duration_s: Decimal = Decimal("0")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    raw: dict = Field(default_factory=dict)


class PrintJobLinkIn(BaseModel):
    quote_id: str
    spool_id: str
```

- [ ] **Step 3: Escrever a rota de ingestão (falha primeiro por ainda não existir)**

Criar `backend/api/routes/printer.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session
from backend.api.schemas.printer import PrintJobIn
from backend.core.models import PrinterJobStatus
from backend.infra.db.models import PrinterJob
from backend.settings import get_settings

ingest_router = APIRouter()

_ALLOWED_STATUS = {"completed", "cancelled", "error"}


def _require_agent(request: Request) -> None:
    token = get_settings().agent_ingest_token
    if not token:
        raise HTTPException(503, "ingest not configured")
    header = request.headers.get("authorization", "")
    if header != f"Bearer {token}":
        raise HTTPException(401, "invalid agent token")


@ingest_router.post("/print-jobs", status_code=201)
async def ingest_print_job(
    payload: PrintJobIn,
    request: Request,
    session: AsyncSession = Depends(db_session),
):
    _require_agent(request)
    if payload.status not in _ALLOWED_STATUS:
        raise HTTPException(422, f"unknown status '{payload.status}'")

    existing = await session.scalar(
        select(PrinterJob).where(
            PrinterJob.machine == payload.machine,
            PrinterJob.job_uid == payload.job_uid,
        )
    )
    if existing:
        # Idempotente: nunca sobrescreve; devolve o registro já conhecido.
        return {"id": str(existing.id), "inbox_status": existing.inbox_status}

    job = PrinterJob(
        machine=payload.machine,
        job_uid=payload.job_uid,
        filename=payload.filename,
        status=payload.status,
        filament_used_mm=payload.filament_used_mm,
        time_s=payload.print_duration_s,
        started_at=payload.started_at,
        finished_at=payload.finished_at,
        raw=payload.raw,
        inbox_status=PrinterJobStatus.PENDING,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return {"id": str(job.id), "inbox_status": job.inbox_status}
```

- [ ] **Step 4: Registrar o router**

Em `backend/app.py`, adicionar `printer` ao import de `backend.api.routes` e registrar após a linha do `inbox`:

```python
app.include_router(printer.ingest_router, prefix="/ingest", tags=["ingest"])
```

- [ ] **Step 5: Escrever os testes de ingestão**

Adicionar a `backend/tests/api/test_printer_ingest.py`:

```python
from httpx import ASGITransport, AsyncClient

from backend.app import app
from backend.settings import AppSettings


def _payload(**over):
    base = {
        "machine": "K1-oficina",
        "job_uid": "100",
        "filename": "peca.gcode",
        "status": "completed",
        "filament_used_mm": "3000",
        "print_duration_s": "5000",
        "raw": {"src": "moonraker"},
    }
    base.update(over)
    return base


async def _ingest_client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def _token(monkeypatch):
    # força o token conhecido para o app durante o teste
    orig = AppSettings.model_fields["agent_ingest_token"].default
    monkeypatch.setattr(
        AppSettings.model_fields["agent_ingest_token"], "default", "sekret"
    )
    yield "sekret"
    monkeypatch.setattr(AppSettings.model_fields["agent_ingest_token"], "default", orig)


@pytest.mark.asyncio
async def test_ingest_requires_token(_token):
    async with await _ingest_client() as c:
        r = await c.post("/ingest/print-jobs", json=_payload())
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_ingest_rejects_wrong_token(_token):
    async with await _ingest_client() as c:
        r = await c.post(
            "/ingest/print-jobs",
            json=_payload(),
            headers={"authorization": "Bearer nope"},
        )
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_ingest_inserts_and_is_idempotent(_token):
    hdr = {"authorization": "Bearer sekret"}
    async with await _ingest_client() as c:
        r1 = await c.post("/ingest/print-jobs", json=_payload(job_uid="200"), headers=hdr)
        assert r1.status_code == 201, r1.text
        first_id = r1.json()["id"]
        # reenvio do mesmo (machine, job_uid) não duplica
        r2 = await c.post("/ingest/print-jobs", json=_payload(job_uid="200"), headers=hdr)
        assert r2.status_code == 201
        assert r2.json()["id"] == first_id


@pytest.mark.asyncio
async def test_ingest_rejects_unknown_status(_token):
    hdr = {"authorization": "Bearer sekret"}
    async with await _ingest_client() as c:
        r = await c.post(
            "/ingest/print-jobs", json=_payload(status="printing"), headers=hdr
        )
        assert r.status_code == 422
```

> Nota: `AppSettings` é instanciado por chamada em `get_settings()`, então sobrescrever o `default` do campo afeta as instâncias criadas dentro do request. Se o monkeypatch do default não pegar no seu ambiente, defina `agent_ingest_token` via env var no `docker-compose.yml` do serviço de teste (`AGENT_INGEST_TOKEN=sekret`) e remova a fixture `_token`, usando o valor fixo `"sekret"`.

- [ ] **Step 6: Rodar os testes**

Run:
```bash
docker compose run --rm api pytest backend/tests/api/test_printer_ingest.py -v
```
Expected: todos PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/settings.py backend/api/schemas/printer.py backend/api/routes/printer.py \
  backend/app.py backend/tests/api/test_printer_ingest.py
git commit -m "feat(printer): ingestão POST /ingest/print-jobs (token + idempotente)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Extrair `apply_production` de `t_produce`

Refatoração que preserva comportamento: move a lógica de precondição + débito de spool + transição pra `em_producao` pra uma função reusável, sem commit interno (o caller controla a transação). Coberta pelos testes de produção existentes.

**Files:**
- Modify: `backend/api/routes/quotes.py:694-758`

**Interfaces:**
- Produces: `async def apply_production(session: AsyncSession, q: Quote, assignments: list[ConsumptionAssignment]) -> None` — valida estado (comercial: `aprovado`/`falhou`; pessoal: `draft`/`falhou` + materiais resolvidos + `finalized_at`), debita cada spool, cria `MaterialConsumption`, seta `q.status = EM_PRODUCAO`. **Não** commita. Levanta `HTTPException` nas violações.

- [ ] **Step 1: Extrair a função**

Em `backend/api/routes/quotes.py`, criar `apply_production` com o corpo hoje inline em `t_produce` (linhas ~708-756), do check de `kind` até `q.status = QuoteStatus.EM_PRODUCAO` (inclusive), removendo o `await session.commit()`:

```python
async def apply_production(
    session: AsyncSession, q: Quote, assignments: list[ConsumptionAssignment]
) -> None:
    if q.kind == QuoteKind.COMMERCIAL:
        if q.status not in (QuoteStatus.APROVADO, QuoteStatus.FALHOU):
            raise HTTPException(409, "quote must be aprovado (ou falhou) before produce")
    elif q.kind == QuoteKind.PERSONAL:
        if q.status not in (QuoteStatus.DRAFT, QuoteStatus.FALHOU):
            raise HTTPException(409, "personal quote must be in draft (ou falhou) to produce")
        await _assert_materials_resolved(session, q)
        if q.finalized_at is None:
            q.finalized_at = _now()
    else:
        raise HTTPException(400, "unsupported quote kind for produce")

    for assign in assignments:
        it = await session.get(QuoteItem, UUID(assign.quote_item_id))
        sp = await session.get(Spool, UUID(assign.spool_id))
        if not it or it.quote_id != q.id or not sp:
            raise HTTPException(400, "invalid assignment")
        mv = await session.get(MaterialVersion, it.material_version_id)
        if assign.grams is not None and assign.grams > 0:
            grams = assign.grams
        else:
            if assign.filament_m is not None and assign.filament_m > 0:
                meta = dict(it.gcode_meta or {})
                meta["filament_m"] = float(assign.filament_m)
                it.gcode_meta = meta
            grams = grams_for_item(it.gcode_meta, mv.density_g_cm3, it.quantity)
        if grams <= 0:
            raise HTTPException(
                409,
                f"item '{it.name}' has no filament length (filament_m=0); "
                "informe a metragem ou as gramas a debitar para produzir",
            )
        if sp.remaining_grams < grams:
            raise HTTPException(409, f"spool {sp.id} has insufficient grams")
        sp.remaining_grams = sp.remaining_grams - grams
        if sp.remaining_grams <= 0:
            sp.status = SpoolStatus.EMPTY
        unit_cost = sp.purchased_price / sp.initial_grams
        session.add(
            MaterialConsumption(
                quote_item_id=it.id,
                spool_id=sp.id,
                grams_used=grams,
                unit_cost_snapshot=unit_cost,
            )
        )
    q.status = QuoteStatus.EM_PRODUCAO
```

- [ ] **Step 2: Reduzir `t_produce` para chamar o helper**

O corpo de `t_produce` passa a ser:

```python
@router.post("/{quote_id}/transitions/produce", response_model=QuoteOut)
async def t_produce(
    quote_id: UUID,
    payload: ProduceRequest,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    await apply_production(session, q, payload.consumption)
    await session.commit()
    return await _quote_out(session, q)
```

- [ ] **Step 3: Rodar os testes de produção existentes**

Run:
```bash
docker compose run --rm api pytest backend/tests/api/test_production_flow.py backend/tests/api/test_quotes_personal.py backend/tests/api/test_quotes_lifecycle.py -v
```
Expected: todos PASS (comportamento preservado).

- [ ] **Step 4: Commit**

```bash
git add backend/api/routes/quotes.py
git commit -m "refactor(produce): extrai apply_production reusável (sem commit interno)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `GET /printer-jobs` + `DELETE /printer-jobs/{id}`

**Files:**
- Modify: `backend/api/routes/printer.py`
- Modify: `backend/app.py`
- Test: `backend/tests/api/test_printer_link.py`

**Interfaces:**
- Consumes: `PrinterJob`, `PrinterJobStatus`, `require_user`, `db_session`.
- Produces: `router` (APIRouter, monta em `/printer-jobs`). `GET /printer-jobs` (só PENDING, ordena por `created_at` desc), `DELETE /printer-jobs/{id}` (marca DISCARDED, 204).

- [ ] **Step 1: Adicionar `router` com list + discard**

Em `backend/api/routes/printer.py`, adicionar no topo os imports e um segundo router:

```python
from uuid import UUID

from backend.api.deps import require_user
from backend.infra.db.models import User

router = APIRouter()


@router.get("")
async def list_printer_jobs(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    rows = (
        await session.execute(
            select(PrinterJob)
            .where(PrinterJob.inbox_status == PrinterJobStatus.PENDING)
            .order_by(PrinterJob.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": str(r.id),
            "machine": r.machine,
            "filename": r.filename,
            "status": r.status,
            "filament_used_mm": float(r.filament_used_mm),
            "time_s": float(r.time_s),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.delete("/{job_id}", status_code=204)
async def discard_printer_job(
    job_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    rec = await session.get(PrinterJob, job_id)
    if not rec:
        raise HTTPException(404)
    rec.inbox_status = PrinterJobStatus.DISCARDED
    await session.commit()
```

- [ ] **Step 2: Registrar o router de gestão**

Em `backend/app.py`, após o `ingest_router`:

```python
app.include_router(printer.router, prefix="/printer-jobs", tags=["printer-jobs"])
```

- [ ] **Step 3: Escrever os testes**

Criar `backend/tests/api/test_printer_link.py`:

```python
import pytest

from backend.infra.db import session as session_module
from backend.infra.db.models import PrinterJob
from backend.core.models import PrinterJobStatus


async def _mk_job(**over) -> str:
    async with session_module.SessionFactory() as s:
        job = PrinterJob(
            machine="K1", job_uid=over.pop("job_uid", "1"),
            filename="p.gcode", status="completed",
            filament_used_mm=over.pop("filament_used_mm", 3000),
            time_s=5000, raw={},
            inbox_status=over.pop("inbox_status", PrinterJobStatus.PENDING),
        )
        for k, v in over.items():
            setattr(job, k, v)
        s.add(job)
        await s.commit()
        await s.refresh(job)
        return str(job.id)


@pytest.mark.asyncio
async def test_list_shows_only_pending(auth_client):
    pend = await _mk_job(job_uid="p1")
    disc = await _mk_job(job_uid="d1", inbox_status=PrinterJobStatus.DISCARDED)
    r = await auth_client.get("/printer-jobs")
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()}
    assert pend in ids
    assert disc not in ids


@pytest.mark.asyncio
async def test_discard_marks_discarded(auth_client):
    jid = await _mk_job(job_uid="x1")
    r = await auth_client.delete(f"/printer-jobs/{jid}")
    assert r.status_code == 204
    async with session_module.SessionFactory() as s:
        rec = await s.get(PrinterJob, jid)
        assert rec.inbox_status == PrinterJobStatus.DISCARDED
```

- [ ] **Step 4: Rodar os testes**

Run:
```bash
docker compose run --rm api pytest backend/tests/api/test_printer_link.py -v
```
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/printer.py backend/app.py backend/tests/api/test_printer_link.py
git commit -m "feat(printer): GET /printer-jobs + DELETE (descartar)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `POST /printer-jobs/{id}/link` (produz com gramas reais)

**Files:**
- Modify: `backend/api/routes/printer.py`
- Test: `backend/tests/api/test_printer_link.py`

**Interfaces:**
- Consumes: `apply_production` e `ConsumptionAssignment` (de `backend.api.routes.quotes` / `backend.api.schemas.quotes`), `grams_from_meters` (`backend.core.pricing.cost`), `grams_for_item` (`backend.core.quote_service`), `PrintJobLinkIn`.
- Produces: `POST /printer-jobs/{job_id}/link` body `{quote_id, spool_id}` → debita spool com gramas reais, seta `quote_id`, `inbox_status = LINKED`.

- [ ] **Step 1: Escrever o teste (single item) — falha primeiro**

Adicionar a `backend/tests/api/test_printer_link.py` um helper que monta um orçamento pessoal aprovável e o teste de link. Reusa os endpoints REST existentes:

```python
from decimal import Decimal
from backend.core.pricing.cost import grams_from_meters


async def _setup_personal_quote_one_item(auth_client) -> tuple[str, str, Decimal]:
    """Cria material PLA, spool cheio e um quote pessoal com 1 item (metragem
    estimada). Retorna (quote_id, spool_id, densidade)."""
    density = Decimal("1.24")
    r = await auth_client.post("/materials", json={
        "material_type": "PLA", "name": "PLA", "density_g_cm3": str(density),
        "price_per_kg_ref": "100", "failure_rate_pct": "0",
    })
    assert r.status_code == 201, r.text

    r = await auth_client.post("/spools", json={
        "material_type": "PLA", "purchased_at": "2026-01-01T00:00:00Z",
        "purchased_price": "100", "initial_grams": "1000", "remaining_grams": "1000",
    })
    assert r.status_code == 201, r.text
    spool_id = r.json()["id"]

    r = await auth_client.post("/quotes", json={"kind": "personal"})
    quote_id = r.json()["id"]
    r = await auth_client.post(f"/quotes/{quote_id}/items", json={
        "name": "peca", "quantity": 1, "material_code": "PLA",
        "time_s": 3600, "filament_m": 5.0,
    })
    assert r.status_code in (200, 201), r.text
    return quote_id, spool_id, density


@pytest.mark.asyncio
async def test_link_produces_with_real_grams(auth_client):
    quote_id, spool_id, density = await _setup_personal_quote_one_item(auth_client)
    jid = await _mk_job(job_uid="link1", filament_used_mm=4000)

    r = await auth_client.post(
        f"/printer-jobs/{jid}/link",
        json={"quote_id": quote_id, "spool_id": spool_id},
    )
    assert r.status_code == 200, r.text

    expected = grams_from_meters(4.0, density, Decimal("1.75"))
    # spool debitado exatamente pelas gramas reais convertidas
    sp = (await auth_client.get(f"/spools/{spool_id}")).json()
    assert Decimal(str(sp["remaining_grams"])) == Decimal("1000") - expected
    # quote foi para em_producao e o job ficou LINKED
    q = (await auth_client.get(f"/quotes/{quote_id}")).json()
    assert q["status"] == "em_producao"
    async with session_module.SessionFactory() as s:
        rec = await s.get(PrinterJob, jid)
        assert rec.inbox_status == PrinterJobStatus.LINKED
        assert str(rec.quote_id) == quote_id


@pytest.mark.asyncio
async def test_link_twice_is_blocked(auth_client):
    quote_id, spool_id, _ = await _setup_personal_quote_one_item(auth_client)
    jid = await _mk_job(job_uid="link2", filament_used_mm=2000)
    r1 = await auth_client.post(
        f"/printer-jobs/{jid}/link", json={"quote_id": quote_id, "spool_id": spool_id})
    assert r1.status_code == 200, r1.text
    r2 = await auth_client.post(
        f"/printer-jobs/{jid}/link", json={"quote_id": quote_id, "spool_id": spool_id})
    assert r2.status_code == 409
```

> Verifique o path real de criação de item (`POST /quotes/{id}/items`) e os campos aceitos (`material_code`, `time_s`, `filament_m`) contra `backend/api/routes/quotes.py`; ajuste o payload do helper se o schema divergir. O objetivo do helper é apenas: um quote pessoal em `draft` com 1 item de material resolvido.

- [ ] **Step 2: Rodar e ver falhar**

Run:
```bash
docker compose run --rm api pytest backend/tests/api/test_printer_link.py::test_link_produces_with_real_grams -v
```
Expected: FAIL (404/405 — rota de link inexistente).

- [ ] **Step 3: Implementar a rota de link**

Em `backend/api/routes/printer.py`, adicionar imports e a rota. A alocação por item é proporcional às gramas estimadas (fallback: divisão igual); cada fatia de `mm` vira gramas com a densidade **daquele** item:

```python
from sqlalchemy.orm import ...  # (não necessário; usar select)

from backend.api.routes.quotes import apply_production
from backend.api.schemas.printer import PrintJobLinkIn
from backend.api.schemas.quotes import ConsumptionAssignment
from backend.core.pricing.cost import grams_from_meters
from backend.core.quote_service import grams_for_item
from backend.infra.db.models import MaterialVersion, Quote, QuoteItem
from decimal import Decimal

_DIAMETER = Decimal("1.75")


@router.post("/{job_id}/link")
async def link_printer_job(
    job_id: UUID,
    payload: PrintJobLinkIn,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    job = await session.get(PrinterJob, job_id)
    if not job or job.inbox_status != PrinterJobStatus.PENDING:
        raise HTTPException(409, "job not pending")
    q = await session.get(Quote, UUID(payload.quote_id))
    if not q:
        raise HTTPException(404, "quote not found")

    items = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == q.id))
    ).scalars().all()
    if not items:
        raise HTTPException(409, "quote has no items")

    # pesos por item = gramas estimadas (fallback: peso igual)
    weights: list[Decimal] = []
    densities: list[Decimal] = []
    for it in items:
        mv = await session.get(MaterialVersion, it.material_version_id)
        if not mv:
            raise HTTPException(409, f"item '{it.name}' has unresolved material")
        densities.append(mv.density_g_cm3)
        est = grams_for_item(it.gcode_meta, mv.density_g_cm3, it.quantity)
        weights.append(est if est > 0 else Decimal("0"))
    total_w = sum(weights)
    n = len(items)

    total_mm = Decimal(str(job.filament_used_mm))
    total_s = Decimal(str(job.time_s))

    assignments: list[ConsumptionAssignment] = []
    total_grams = Decimal("0")
    for idx, it in enumerate(items):
        frac = (weights[idx] / total_w) if total_w > 0 else (Decimal("1") / n)
        item_mm = total_mm * frac
        item_grams = grams_from_meters(float(item_mm) / 1000.0, densities[idx], _DIAMETER)
        total_grams += item_grams
        # persiste real (gramas + tempo) no gcode_meta p/ o analítico de variância
        meta = dict(it.gcode_meta or {})
        meta["filament_g"] = float(item_grams)
        meta["time_s"] = float(total_s * frac)
        it.gcode_meta = meta
        assignments.append(
            ConsumptionAssignment(
                quote_item_id=str(it.id),
                spool_id=payload.spool_id,
                grams=item_grams,
            )
        )

    await apply_production(session, q, assignments)
    job.inbox_status = PrinterJobStatus.LINKED
    job.quote_id = q.id
    job.grams = total_grams
    await session.commit()
    return {"quote_id": str(q.id), "grams": float(total_grams), "status": q.status}
```

- [ ] **Step 4: Rodar os testes de link**

Run:
```bash
docker compose run --rm api pytest backend/tests/api/test_printer_link.py -v
```
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/printer.py backend/tests/api/test_printer_link.py
git commit -m "feat(printer): POST /printer-jobs/{id}/link — produz com gramas reais + baixa spool

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Alocação multi-item (proporcional) — teste dedicado

Valida a distribuição já implementada na Task 5 num quote com 2 itens de gramas estimadas diferentes.

**Files:**
- Test: `backend/tests/api/test_printer_link.py`

- [ ] **Step 1: Escrever o teste multi-item**

Adicionar a `backend/tests/api/test_printer_link.py`:

```python
@pytest.mark.asyncio
async def test_link_multi_item_proportional(auth_client):
    density = Decimal("1.24")
    await auth_client.post("/materials", json={
        "material_type": "PLA", "name": "PLA", "density_g_cm3": str(density),
        "price_per_kg_ref": "100", "failure_rate_pct": "0"})
    r = await auth_client.post("/spools", json={
        "material_type": "PLA", "purchased_at": "2026-01-01T00:00:00Z",
        "purchased_price": "100", "initial_grams": "1000", "remaining_grams": "1000"})
    spool_id = r.json()["id"]

    r = await auth_client.post("/quotes", json={"kind": "personal"})
    quote_id = r.json()["id"]
    # item A estima 2x o item B (filament_m 6 vs 3)
    await auth_client.post(f"/quotes/{quote_id}/items", json={
        "name": "A", "quantity": 1, "material_code": "PLA", "time_s": 100, "filament_m": 6.0})
    await auth_client.post(f"/quotes/{quote_id}/items", json={
        "name": "B", "quantity": 1, "material_code": "PLA", "time_s": 100, "filament_m": 3.0})

    jid = await _mk_job(job_uid="multi1", filament_used_mm=9000)
    r = await auth_client.post(
        f"/printer-jobs/{jid}/link", json={"quote_id": quote_id, "spool_id": spool_id})
    assert r.status_code == 200, r.text

    # A recebe 2/3 de 9000mm = 6000mm; B recebe 3000mm
    from backend.core.pricing.cost import grams_from_meters
    expected = (grams_from_meters(6.0, density, Decimal("1.75"))
                + grams_from_meters(3.0, density, Decimal("1.75")))
    sp = (await auth_client.get(f"/spools/{spool_id}")).json()
    assert Decimal(str(sp["remaining_grams"])) == Decimal("1000") - expected
```

- [ ] **Step 2: Rodar**

Run:
```bash
docker compose run --rm api pytest backend/tests/api/test_printer_link.py::test_link_multi_item_proportional -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/api/test_printer_link.py
git commit -m "test(printer): alocação proporcional multi-item no link

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Frontend — aba "Impressora"

Nova página que lista os `printer_jobs` PENDING e permite linkar (seletor de orçamento + spool). Segue o padrão visual de `frontend/src/routes/inbox/+page.svelte`. **Usar a skill `frontend-design` ao construir a UI.**

**Files:**
- Modify: `frontend/src/lib/types.ts`
- Create: `frontend/src/routes/printer-jobs/+page.svelte`
- Modify: `frontend/src/routes/+layout.svelte`

- [ ] **Step 1: Adicionar o tipo**

Em `frontend/src/lib/types.ts`, adicionar:

```ts
export interface PrinterJobItem {
  id: string;
  machine: string;
  filename: string | null;
  status: string;
  filament_used_mm: number;
  time_s: number;
  created_at: string | null;
}
```

- [ ] **Step 2: Criar a página**

Criar `frontend/src/routes/printer-jobs/+page.svelte` seguindo o padrão do inbox: `onMount` → `requireAuth()` + carrega `GET /printer-jobs`, `GET /quotes` (para o seletor) e `GET /spools`. Cada linha mostra `filename`, `machine`, `filament_used_mm`, `time_s`, com botões "linkar" (abre modal com `<select>` de orçamento e `<select>` de spool → `POST /printer-jobs/{id}/link` com `{quote_id, spool_id}`) e "descartar" (`DELETE /printer-jobs/{id}`). Reusar os helpers `fmtNum`/`fmtDur`/`fmtDate` e o markup `.table-wrap`/`.modal-backdrop`/`.modal` do inbox. Header:

```svelte
<header class="page-head">
  <span class="page-eyebrow">Captura / 04</span>
  <h1 class="page-title">Impressora<em>.</em></h1>
  <p class="page-lede">
    Jobs finalizados capturados da impressora. Vincule cada um a um orçamento e
    escolha o filamento usado — a baixa de estoque usa as gramas reais.
  </p>
</header>
```

O modal de link (essência):

```svelte
<label class="field full">
  Orçamento
  <select bind:value={lQuote}>
    <option value="">— escolha —</option>
    {#each quotes as q}
      <option value={q.id}>{q.id.slice(0, 8)} · {q.status}</option>
    {/each}
  </select>
</label>
<label class="field full">
  Filamento (spool)
  <select bind:value={lSpool}>
    <option value="">— escolha —</option>
    {#each spools as sp}
      <option value={sp.id}>{sp.material_type} {sp.color ?? ""} · {sp.remaining_grams}g</option>
    {/each}
  </select>
</label>
```

Função de confirmação:

```ts
async function confirmLink() {
  if (!linking || !lQuote || !lSpool) return;
  lSubmitting = true;
  try {
    await api(`/printer-jobs/${linking.id}/link`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ quote_id: lQuote, spool_id: lSpool }),
    });
    linking = null;
    await load();
  } catch (err) {
    handleApiError(err);
    lError = errorMessage(err, "Falha ao vincular.");
  } finally {
    lSubmitting = false;
  }
}
```

- [ ] **Step 3: Adicionar link de navegação**

Em `frontend/src/routes/+layout.svelte`, adicionar um item de navegação para `/printer-jobs` ao lado do link de `/inbox` (seguir o markup dos links existentes).

- [ ] **Step 4: Verificação manual**

Rodar o app (skill `run`) e confirmar: a página `/printer-jobs` carrega, lista um job inserido via ingestão, o modal de link mostra orçamentos e spools, e ao confirmar o job some da lista e o orçamento vai pra `em_producao`. Verificar o build:

```bash
cd frontend && npm run build
```
Expected: build sem erros de tipo.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/routes/printer-jobs/+page.svelte \
  frontend/src/routes/+layout.svelte
git commit -m "feat(printer): aba Impressora — lista e vincula jobs a orçamento

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- §3/§5 ingestão (token, idempotência, insert) → Task 2. ✓
- §6 tabela `printer_jobs` → Task 1. ✓
- §7 conversão mm→gramas → Task 5 (`grams_from_meters`). ✓
- §8 link = produce real (precondição, débito, alocação 1/N itens, LINKED, re-link 409) → Tasks 3, 5, 6. ✓
- §9 UX aba Impressora → Task 7. ✓
- §10 segurança (token em env) → Task 2. ✓
- §11 testes (conversão coberta no link; ingestão idempotência/auth/status; link débito/estado/alocação) → Tasks 2, 5, 6. ✓
- §4 escopo agente (repo separado) → fora deste plano por design. ✓

**Placeholder scan:** sem TODOs/TBDs; todo passo de código traz o código. O único ponto marcado como "verifique/ajuste" é o payload de criação de item no helper de teste (Task 5 Step 1), porque o schema de item não foi lido integralmente — a nota diz exatamente o que confirmar.

**Type consistency:** `apply_production(session, q, assignments)` definido na Task 3 e consumido na Task 5 com a mesma assinatura; `ConsumptionAssignment(quote_item_id, spool_id, grams)` bate com `backend/api/schemas/quotes.py`; `PrinterJobStatus.{PENDING,LINKED,DISCARDED}` consistente entre model, rotas e testes; `ingest_router`/`router` nomeados igual em `printer.py` e `app.py`.

**Nota de risco (Task 2):** o override de `agent_ingest_token` via monkeypatch do default pode não pegar em todos os setups — a nota no Step 5 dá o plano B (env var no compose de teste).
