# Atribuição de projetos pessoais — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Marcar de quem é cada projeto pessoal (1+ pessoas de uma lista configurável), editável em qualquer status, alimentando o export pro Databricks e um dashboard nos Insights.

**Architecture:** Tabelas `people` (configurável) + `quote_people` (N:N). CRUD de pessoas em `/people`. Atribuição via `PUT /quotes/{id}/people` (sem gate de status, só personal). Agregação num módulo `core/insights/personal_projects.py` exposto em `/insights/personal-projects`. Export ganha as duas entidades.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic, pytest via Docker, SvelteKit.

**Spec:** `docs/superpowers/specs/2026-06-25-projetos-pessoais-atribuicao-design.md`

**Comandos:** testes/lint/migração via `docker compose run --rm api …`.

---

## File Structure

- `backend/infra/db/models/person.py` — `Person`; `quote_person.py` — `QuotePerson` (+ exports no `__init__`).
- `migrations/versions/0029_people_quote_people.py`
- `backend/api/schemas/people.py` — `PersonOut/Create/Update`; `quotes.py` — `QuotePeopleUpdate`, `person_ids` no `QuoteOut`.
- `backend/api/routes/people.py` — CRUD; `quotes.py` — `PUT /{id}/people` + wiring; `app.py` — registra `/people`.
- `backend/core/insights/personal_projects.py` — agregação; `insights.py` — endpoint.
- `backend/core/export/entities.py` — entidades novas.
- `backend/tests/api/conftest.py` — cleanup.
- Frontend: `lib/types.ts`, `settings/+page.svelte`, `quotes/[id]/+page.svelte`, `quotes/+page.svelte`, `insights/+page.svelte`.

---

## Task 1: Models + migração (`people`, `quote_people`)

**Files:**
- Create: `backend/infra/db/models/person.py`, `backend/infra/db/models/quote_person.py`, `migrations/versions/0029_people_quote_people.py`
- Modify: `backend/infra/db/models/__init__.py`, `backend/tests/api/conftest.py`

- [ ] **Step 1: Models**

`backend/infra/db/models/person.py`:
```python
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, func, true
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class Person(Base):
    """Membro do lar pra atribuir projetos pessoais (Otávio, Ana, …). Rótulo
    analítico, desacoplado de `users`."""
    __tablename__ = "people"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

`backend/infra/db/models/quote_person.py`:
```python
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class QuotePerson(Base):
    """Join N:N orçamento pessoal ↔ pessoa."""
    __tablename__ = "quote_people"

    quote_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
```

- [ ] **Step 2: Exports no `__init__`**

Em `backend/infra/db/models/__init__.py`, adicionar imports (ordem alfabética perto dos `quote_*`):
```python
from backend.infra.db.models.person import Person
from backend.infra.db.models.quote_person import QuotePerson
```
e `"Person"`, `"QuotePerson"` no `__all__`.

- [ ] **Step 3: Migração**

`migrations/versions/0029_people_quote_people.py`:
```python
"""people + quote_people (atribuição de projeto pessoal)

Revision ID: 0029_people_quote_people
Revises: 0028_quote_photos
Create Date: 2026-06-25 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0029_people_quote_people"
down_revision: Union[str, Sequence[str], None] = "0028_quote_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "people",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_people_name", "people", ["name"])
    op.create_table(
        "quote_people",
        sa.Column("quote_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("quotes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("person_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("people.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("quote_people")
    op.drop_table("people")
```

- [ ] **Step 4: Cleanup nos testes**

Em `backend/tests/api/conftest.py`: importar `Person`, `QuotePerson` e adicionar `QuotePerson.__table__` **antes** de `Quote.__table__` (FK), e `Person.__table__` logo depois do join.

- [ ] **Step 5: Aplicar**

Run: `docker compose run --rm api alembic upgrade head`
Expected: aplica `0029_people_quote_people` sem erro.

- [ ] **Step 6: Commit**
```bash
git add backend/infra/db/models/person.py backend/infra/db/models/quote_person.py backend/infra/db/models/__init__.py migrations/versions/0029_people_quote_people.py backend/tests/api/conftest.py
git commit -m "feat(pessoais): migração + models Person/QuotePerson"
```

---

## Task 2: People CRUD API

**Files:**
- Create: `backend/api/schemas/people.py`, `backend/api/routes/people.py`
- Modify: `backend/app.py`
- Test: `backend/tests/api/test_people.py`

- [ ] **Step 1: Teste**

`backend/tests/api/test_people.py`:
```python
import pytest


@pytest.mark.asyncio
async def test_people_crud(auth_client):
    r = await auth_client.post("/people", json={"name": "Otávio"})
    assert r.status_code == 201, r.text
    otavio = r.json()
    assert otavio["name"] == "Otávio" and otavio["active"] is True

    await auth_client.post("/people", json={"name": "Ana"})

    # nome duplicado -> 409
    dup = await auth_client.post("/people", json={"name": "Otávio"})
    assert dup.status_code == 409

    lst = (await auth_client.get("/people")).json()
    assert {p["name"] for p in lst} == {"Otávio", "Ana"}

    # inativa
    upd = await auth_client.put(f"/people/{otavio['id']}", json={"active": False})
    assert upd.status_code == 200 and upd.json()["active"] is False

    # apaga
    d = await auth_client.delete(f"/people/{otavio['id']}")
    assert d.status_code == 204
    lst2 = (await auth_client.get("/people")).json()
    assert {p["name"] for p in lst2} == {"Ana"}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_people.py -q`
Expected: FAIL — 404.

- [ ] **Step 3: Schema**

`backend/api/schemas/people.py`:
```python
from pydantic import BaseModel


class PersonOut(BaseModel):
    id: str
    name: str
    active: bool
    sort_order: int


class PersonCreate(BaseModel):
    name: str


class PersonUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None
    sort_order: int | None = None
```

- [ ] **Step 4: Route**

`backend/api/routes/people.py`:
```python
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import db_session, require_user
from backend.api.schemas.people import PersonCreate, PersonOut, PersonUpdate
from backend.infra.db.models import Person, User

router = APIRouter()


def _out(p: Person) -> PersonOut:
    return PersonOut(id=str(p.id), name=p.name, active=p.active, sort_order=p.sort_order)


@router.get("", response_model=list[PersonOut])
async def list_people(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    rows = (await session.execute(select(Person).order_by(Person.sort_order, Person.name))).scalars().all()
    return [_out(p) for p in rows]


@router.post("", response_model=PersonOut, status_code=201)
async def create_person(payload: PersonCreate, _: User = Depends(require_user),
                        session: AsyncSession = Depends(db_session)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "nome vazio")
    exists = (await session.execute(select(Person).where(Person.name == name))).scalar_one_or_none()
    if exists:
        raise HTTPException(409, "já existe pessoa com esse nome")
    p = Person(name=name)
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return _out(p)


@router.put("/{person_id}", response_model=PersonOut)
async def update_person(person_id: UUID, payload: PersonUpdate, _: User = Depends(require_user),
                        session: AsyncSession = Depends(db_session)):
    p = await session.get(Person, person_id)
    if not p:
        raise HTTPException(404)
    if payload.name is not None:
        p.name = payload.name.strip()
    if payload.active is not None:
        p.active = payload.active
    if payload.sort_order is not None:
        p.sort_order = payload.sort_order
    await session.commit()
    await session.refresh(p)
    return _out(p)


@router.delete("/{person_id}", status_code=204)
async def delete_person(person_id: UUID, _: User = Depends(require_user),
                        session: AsyncSession = Depends(db_session)):
    p = await session.get(Person, person_id)
    if not p:
        raise HTTPException(404)
    await session.delete(p)
    await session.commit()
    return Response(status_code=204)
```

- [ ] **Step 5: Registrar no app**

Em `backend/app.py`, junto dos outros `include_router` e imports:
```python
from backend.api.routes import people
...
app.include_router(people.router, prefix="/people", tags=["people"])
```
(seguir o padrão de import existente do módulo — conferir como os outros routes são importados no topo de `app.py` e imitar.)

- [ ] **Step 6: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_people.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**
```bash
git add backend/api/schemas/people.py backend/api/routes/people.py backend/app.py backend/tests/api/test_people.py
git commit -m "feat(pessoais): CRUD de pessoas (/people)"
```

---

## Task 3: Atribuição pessoa↔orçamento

**Files:**
- Modify: `backend/api/schemas/quotes.py`, `backend/api/routes/quotes.py`
- Test: `backend/tests/api/test_quote_people.py`

- [ ] **Step 1: Schema**

Em `backend/api/schemas/quotes.py`, adicionar:
```python
class QuotePeopleUpdate(BaseModel):
    person_ids: list[str]
```
e no `QuoteOut`, adicionar o campo (no fim da classe):
```python
    person_ids: list[str] = []
```

- [ ] **Step 2: Teste**

`backend/tests/api/test_quote_people.py`:
```python
import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Person, Quote, User


async def _person(name):
    async with session_module.SessionFactory() as s:
        p = Person(name=name)
        s.add(p); await s.commit()
        return str(p.id)


async def _quote(kind, status):
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=kind, user_id=u.id, status=status)
        s.add(q); await s.commit()
        return str(q.id)


@pytest.mark.asyncio
async def test_set_people_on_finished_personal_quote(auth_client):
    pid1 = await _person("Otávio")
    pid2 = await _person("Ana")
    qid = await _quote(QuoteKind.PERSONAL.value, QuoteStatus.ENTREGUE.value)  # finalizado

    r = await auth_client.put(f"/quotes/{qid}/people", json={"person_ids": [pid1, pid2]})
    assert r.status_code == 200, r.text
    assert set(r.json()["person_ids"]) == {pid1, pid2}

    # reescreve (só um agora)
    r = await auth_client.put(f"/quotes/{qid}/people", json={"person_ids": [pid1]})
    assert r.json()["person_ids"] == [pid1]

    # persiste no GET
    assert (await auth_client.get(f"/quotes/{qid}")).json()["person_ids"] == [pid1]


@pytest.mark.asyncio
async def test_people_rejected_on_commercial(auth_client):
    pid = await _person("Otávio")
    qid = await _quote(QuoteKind.COMMERCIAL.value, QuoteStatus.DRAFT.value)
    r = await auth_client.put(f"/quotes/{qid}/people", json={"person_ids": [pid]})
    assert r.status_code == 400, r.text
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_quote_people.py -q`
Expected: FAIL — 404 / `person_ids` ausente.

- [ ] **Step 4: Imports + wiring + rota**

Em `backend/api/routes/quotes.py`:
- No import do sqlalchemy, adicionar `delete`: `from sqlalchemy import delete, func, select`.
- No import de models, adicionar `Person, QuotePerson`.
- No import de schemas, adicionar `QuotePeopleUpdate`.

No `_quote_out`, antes do `return QuoteOut(...)`, carregar as pessoas:
```python
    person_rows = (await session.execute(
        select(QuotePerson.person_id).where(QuotePerson.quote_id == q.id)
    )).scalars().all()
    person_ids = [str(pid) for pid in person_rows]
```
e no `QuoteOut(...)` adicionar `person_ids=person_ids,`.

Rota nova (perto das outras de `quotes`):
```python
@router.put("/{quote_id}/people", response_model=QuoteOut)
async def set_quote_people(
    quote_id: UUID,
    payload: QuotePeopleUpdate,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    if q.kind != QuoteKind.PERSONAL.value:
        raise HTTPException(400, "atribuição de pessoa só para orçamento pessoal")
    ids = [UUID(x) for x in payload.person_ids]
    if ids:
        found = set((await session.execute(
            select(Person.id).where(Person.id.in_(ids))
        )).scalars().all())
        if found != set(ids):
            raise HTTPException(400, "pessoa inexistente")
    await session.execute(delete(QuotePerson).where(QuotePerson.quote_id == q.id))
    for pid in ids:
        session.add(QuotePerson(quote_id=q.id, person_id=pid))
    await session.commit()
    return await _quote_out(session, q)
```
NOTA: `QuoteKind` já está importado no módulo.

- [ ] **Step 5: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_quote_people.py -q`
Expected: PASS (2).

- [ ] **Step 6: Commit**
```bash
git add backend/api/schemas/quotes.py backend/api/routes/quotes.py backend/tests/api/test_quote_people.py
git commit -m "feat(pessoais): PUT /quotes/{id}/people (qualquer status) + person_ids no QuoteOut"
```

---

## Task 4: Insights — agregação por pessoa

**Files:**
- Create: `backend/core/insights/__init__.py` (se não existir), `backend/core/insights/personal_projects.py`
- Modify: `backend/api/routes/insights.py`
- Test: `backend/tests/core/test_personal_projects.py`

- [ ] **Step 1: Teste**

`backend/tests/core/test_personal_projects.py`:
```python
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.core.insights.personal_projects import compute_personal_projects
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialConsumption, Person, Quote, QuoteItem, QuotePerson, Spool, User,
)


@pytest.mark.asyncio
async def test_counts_grams_and_shared():
    async with session_module.SessionFactory() as s:
        u = User(name="u", email="pp@t.com", password_hash="x")
        s.add(u); await s.commit()
        otavio = Person(name="Otávio"); ana = Person(name="Ana")
        s.add_all([otavio, ana]); await s.commit()

        # projeto só do Otávio, com 100g de material
        q1 = Quote(kind=QuoteKind.PERSONAL.value, user_id=u.id, status=QuoteStatus.PRODUZIDO.value)
        # projeto compartilhado (Otávio + Ana)
        q2 = Quote(kind=QuoteKind.PERSONAL.value, user_id=u.id, status=QuoteStatus.PRODUZIDO.value)
        s.add_all([q1, q2]); await s.commit()
        s.add_all([
            QuotePerson(quote_id=q1.id, person_id=otavio.id),
            QuotePerson(quote_id=q2.id, person_id=otavio.id),
            QuotePerson(quote_id=q2.id, person_id=ana.id),
        ])
        item = QuoteItem(quote_id=q1.id, name="p", gcode_meta={}, quantity=1)
        spool = Spool(material_type="PLA", purchased_at=date(2026, 6, 1),
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("900"))
        s.add_all([item, spool]); await s.commit()
        s.add(MaterialConsumption(quote_item_id=item.id, spool_id=spool.id,
                                  grams_used=Decimal("100"), unit_cost_snapshot=Decimal("0.50"),
                                  consumed_at=datetime(2026, 6, 12, tzinfo=timezone.utc)))
        await s.commit()

    async with session_module.SessionFactory() as s:
        res = await compute_personal_projects(s, date(2026, 1, 1), date(2026, 12, 31))

    by_name = {p["name"]: p for p in res["people"]}
    assert by_name["Otávio"]["count"] == 2          # q1 + q2 (compartilhado conta)
    assert by_name["Ana"]["count"] == 1
    assert by_name["Otávio"]["grams"] == Decimal("100.00")
    assert res["shared_count"] == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_personal_projects.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

`backend/core/insights/__init__.py`: criar vazio se não existir.

`backend/core/insights/personal_projects.py`:
```python
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import QuoteKind
from backend.infra.db.models import (
    MaterialConsumption, Person, Quote, QuoteItem, QuotePerson, Sale,
)


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"))


async def compute_personal_projects(session: AsyncSession, period_from: date, period_to: date) -> dict:
    """Agrega projetos pessoais por pessoa no período (por created_at do orçamento).

    Projeto compartilhado (2+ pessoas) conta para cada uma; `shared_count` e
    `unassigned_count` dão a leitura honesta.
    """
    next_day = period_to + timedelta(days=1)
    quotes = (await session.execute(
        select(Quote).where(
            Quote.kind == QuoteKind.PERSONAL.value,
            Quote.created_at >= period_from,
            Quote.created_at < next_day,
        )
    )).scalars().all()
    quote_ids = [q.id for q in quotes]
    if not quote_ids:
        return {"people": [], "shared_count": 0, "unassigned_count": 0}

    qp = (await session.execute(
        select(QuotePerson).where(QuotePerson.quote_id.in_(quote_ids))
    )).scalars().all()
    people_by_quote: dict = defaultdict(list)
    for row in qp:
        people_by_quote[row.quote_id].append(row.person_id)

    grams_rows = (await session.execute(
        select(QuoteItem.quote_id, func.coalesce(func.sum(MaterialConsumption.grams_used), 0))
        .join(MaterialConsumption, MaterialConsumption.quote_item_id == QuoteItem.id)
        .where(QuoteItem.quote_id.in_(quote_ids))
        .group_by(QuoteItem.quote_id)
    )).all()
    grams_by_quote = {qid: Decimal(g) for qid, g in grams_rows}

    sales = (await session.execute(
        select(Sale).where(Sale.quote_id.in_(quote_ids), Sale.is_stale.is_(False))
    )).scalars().all()
    cpv_by_quote = {
        s.quote_id: (s.cpv_override if s.cpv_override is not None else s.cpv_calc)
        for s in sales
    }

    name_by_id = {
        p.id: p.name
        for p in (await session.execute(select(Person))).scalars().all()
    }

    agg: dict = {}
    shared = 0
    unassigned = 0
    for q in quotes:
        pids = people_by_quote.get(q.id, [])
        if not pids:
            unassigned += 1
            continue
        if len(pids) >= 2:
            shared += 1
        month = q.created_at.strftime("%Y-%m")
        g = grams_by_quote.get(q.id, Decimal(0))
        c = cpv_by_quote.get(q.id, Decimal(0))
        for pid in pids:
            a = agg.setdefault(pid, {"count": 0, "grams": Decimal(0), "cpv": Decimal(0),
                                     "monthly": defaultdict(int)})
            a["count"] += 1
            a["grams"] += g
            a["cpv"] += c
            a["monthly"][month] += 1

    people = []
    for pid, a in agg.items():
        people.append({
            "person_id": str(pid),
            "name": name_by_id.get(pid, "—"),
            "count": a["count"],
            "grams": _q2(a["grams"]),
            "cpv": _q2(a["cpv"]),
            "monthly": [{"month": m, "count": n} for m, n in sorted(a["monthly"].items())],
        })
    people.sort(key=lambda x: x["count"], reverse=True)
    return {"people": people, "shared_count": shared, "unassigned_count": unassigned}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_personal_projects.py -q`
Expected: PASS.

- [ ] **Step 5: Endpoint**

Em `backend/api/routes/insights.py`:
- Adicionar `Query` ao import do fastapi: `from fastapi import APIRouter, Depends, HTTPException, Query`.
- Adicionar `from datetime import date` (já tem `datetime, timedelta, timezone`; garantir `date`).
- Import: `from backend.core.insights.personal_projects import compute_personal_projects`.

Endpoint:
```python
@router.get("/personal-projects")
async def personal_projects(
    period_from: date | None = Query(None),
    period_to: date | None = Query(None),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    pt = period_to or _now().date()
    pf = period_from or (pt - timedelta(days=365))
    return await compute_personal_projects(session, pf, pt)
```

- [ ] **Step 6: Smoke do endpoint**

Run: `docker compose run --rm api pytest backend/tests/core/test_personal_projects.py -q` (core já cobre a lógica). Opcional: `curl` manual depois de subir.

- [ ] **Step 7: Commit**
```bash
git add backend/core/insights/__init__.py backend/core/insights/personal_projects.py backend/api/routes/insights.py backend/tests/core/test_personal_projects.py
git commit -m "feat(pessoais): insights /personal-projects (contagem/gramas/cpv/mensal por pessoa)"
```

---

## Task 5: Export das entidades novas

**Files:**
- Modify: `backend/core/export/entities.py`
- Test: `backend/tests/core/test_export_entities.py` (adicionar asserção)

- [ ] **Step 1: Teste (estender o existente)**

Em `backend/tests/core/test_export_entities.py`, adicionar ao teste de nomes:
```python
def test_people_entities_exported():
    from backend.core.export.entities import EXPORT_ENTITIES
    names = {name for name, _m, _ex in EXPORT_ENTITIES}
    assert "people" in names
    assert "quote_people" in names
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_entities.py::test_people_entities_exported -q`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Em `backend/core/export/entities.py`: adicionar `Person, QuotePerson` ao import de models e duas tuplas em `EXPORT_ENTITIES`:
```python
    ("people", Person, set()),
    ("quote_people", QuotePerson, set()),
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_entities.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add backend/core/export/entities.py backend/tests/core/test_export_entities.py
git commit -m "feat(pessoais): exporta people + quote_people pro data lake"
```

---

## Task 6: Frontend

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/routes/settings/+page.svelte`, `frontend/src/routes/quotes/[id]/+page.svelte`, `frontend/src/routes/quotes/+page.svelte`, `frontend/src/routes/insights/+page.svelte`

- [ ] **Step 1: Tipos**

Em `frontend/src/lib/types.ts`:
```typescript
export type Person = {
  id: string;
  name: string;
  active: boolean;
  sort_order: number;
};
```
e adicionar `person_ids: string[]` ao tipo `Quote` (campo opcional `person_ids?: string[]` pra não quebrar outros usos).

- [ ] **Step 2: Configurações — CRUD de pessoas**

Em `frontend/src/routes/settings/+page.svelte`, adicionar uma `<section class="panel">` "Pessoas (projetos pessoais)" que:
- no `onMount`/load, faz `api<Person[]>("/people")`;
- lista as pessoas com toggle de ativo (PUT `/people/{id}` `{active}`) e botão excluir (DELETE);
- um input + botão "adicionar" (POST `/people` `{name}`).
Seguir o estilo dos painéis/itens já existentes na página. Sem `any`.

- [ ] **Step 3: Orçamento — checkboxes (só personal)**

Em `frontend/src/routes/quotes/[id]/+page.svelte`:
- no load das refs, carregar `people = await api<Person[]>("/people")` (só ativos pra exibir; manter os já marcados mesmo se inativos);
- estado `let selectedPeople: Set<string>` derivado de `quote.person_ids`;
- bloco condicional `{#if quote.kind === "personal"}` "Projeto pessoal de" com um checkbox por pessoa ativa; ao alterar, montar a lista de ids marcados e chamar:
```typescript
  async function savePeople(ids: string[]) {
    quote = await api<Quote>(`/quotes/${id}/people`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ person_ids: ids }),
    });
  }
```
(editável em qualquer status — não gatear por `isDraft`).

- [ ] **Step 4: Lista /quotes — inline (só personal)**

Em `frontend/src/routes/quotes/+page.svelte`, na linha dos orçamentos pessoais, um controle compacto (ex.: dropdown com checkboxes, ou chips clicáveis das pessoas ativas) que chama `PUT /quotes/{id}/people` e atualiza a linha. Carregar `people` no load. Para comercial, não exibir.

- [ ] **Step 5: Insights — painel**

Em `frontend/src/routes/insights/+page.svelte`:
- carregar `const pp = await api<PersonalProjects>("/insights/personal-projects")` (tipar inline ou em types.ts: `{ people: {person_id,name,count,grams,cpv,monthly:{month,count}[]}[], shared_count:number, unassigned_count:number }`);
- painel "Projetos pessoais" com tabela por pessoa (contagem · gramas · custo) ordenada por contagem, e a série mensal (mini-barras ou lista) — seguir o estilo dos painéis existentes;
- mostrar `shared_count` e `unassigned_count` como nota.

- [ ] **Step 6: Check**

Run: `cd frontend && npm run check`
Expected: sem erros novos (só os pré-existentes de library/spools).

- [ ] **Step 7: Commit**
```bash
git add frontend/src/lib/types.ts frontend/src/routes/settings/+page.svelte frontend/src/routes/quotes/[id]/+page.svelte frontend/src/routes/quotes/+page.svelte frontend/src/routes/insights/+page.svelte
git commit -m "feat(pessoais): UI — pessoas em Config, checkboxes no orçamento, inline na lista, painel nos Insights"
```

---

## Task 7: Verificação

- [ ] **Step 1:** `docker compose run --rm api pytest backend/tests -q` → tudo PASS.
- [ ] **Step 2:** `cd frontend && npm run check` → sem erros novos.
- [ ] **Step 3:** `docker compose run --rm api ruff check backend/api/routes/people.py backend/api/routes/quotes.py backend/core/insights/personal_projects.py backend/infra/db/models/person.py backend/infra/db/models/quote_person.py` → sem erros novos.

---

## Notas

- **Compartilhado conta pra cada pessoa** (responde "quem sobe mais"); `shared_count`/`unassigned_count` dão a leitura honesta.
- **Sem seed** de nomes na migração — Otávio cadastra "Otávio"/"Ana" em Configurações.
- **`people`/`quote_people` no export** fluem pro Databricks no próximo run.
- **CPV** vem de `Sale` (override > calc); projeto pessoal sem venda/produção → cpv/grams 0 (esperado).
