# Export para Data Lake (S3/Databricks) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exportar todas as entidades como Parquet bruto (snapshot por timestamp) para um destino configurável (S3 ou volume Databricks), com config/segredos na aba Integrações, botão de export sob demanda e drop diário pausável.

**Architecture:** Tabela singleton `export_config`. Módulo `core/export/` (serialize via pyarrow, registry de entidades, destinos S3/Databricks com interface comum, runner). `execute_export(session)` é a fonte única usada pelo endpoint de force e pelo scheduler diário. Config exposta/mascarada em `/config/export`.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic, pyarrow (Parquet), boto3 (S3), httpx (Databricks Files API), pytest via Docker, SvelteKit.

**Spec:** `docs/superpowers/specs/2026-06-17-export-datalake-design.md`

---

## File Structure

- `backend/infra/db/models/export_config.py` — model `ExportConfig` (+ export no `__init__`).
- `migrations/versions/0027_export_config.py` — tabela.
- `pyproject.toml` — `pyarrow`, `boto3`.
- `backend/core/export/__init__.py`
- `backend/core/export/serialize.py` — `table_to_parquet`.
- `backend/core/export/entities.py` — `EXPORT_ENTITIES`.
- `backend/core/export/destinations.py` — `S3Destination`, `DatabricksDestination`, `build_destination`.
- `backend/core/export/runner.py` — `run_export`, `execute_export`.
- `backend/infra/scheduler/export.py` — `export_once`, `run_forever`, `start_background_task`.
- `backend/api/schemas/config.py` — `ExportConfigOut`, `ExportConfigUpdate`.
- `backend/api/routes/config.py` — `GET/PUT /config/export`, `POST /config/export/run`.
- `backend/app.py` — start do scheduler.
- `frontend/src/lib/types.ts`, `frontend/src/routes/config/+page.svelte` — seção Data Lake.

---

## Task 1: Migração + model `ExportConfig`

**Files:**
- Create: `backend/infra/db/models/export_config.py`, `migrations/versions/0027_export_config.py`
- Modify: `backend/infra/db/models/__init__.py`, `backend/tests/api/conftest.py`

- [ ] **Step 1: Model**

`backend/infra/db/models/export_config.py`:

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class ExportConfig(Base):
    """Config singleton (id=1) do export pro data lake (S3 ou Databricks)."""
    __tablename__ = "export_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    destination: Mapped[str] = mapped_column(String(20), nullable=False, default="s3", server_default="s3")
    s3_bucket: Mapped[str | None] = mapped_column(String(200))
    s3_region: Mapped[str | None] = mapped_column(String(40))
    s3_prefix: Mapped[str | None] = mapped_column(String(300))
    s3_access_key_id: Mapped[str | None] = mapped_column(String(200))
    s3_secret_access_key: Mapped[str | None] = mapped_column(String(300))
    databricks_host: Mapped[str | None] = mapped_column(String(300))
    databricks_token: Mapped[str | None] = mapped_column(String(300))
    databricks_volume_path: Mapped[str | None] = mapped_column(String(400))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_status: Mapped[str | None] = mapped_column(String(20))
    last_run_detail: Mapped[str | None] = mapped_column(Text)
```

- [ ] **Step 2: Export no `__init__`**

Em `backend/infra/db/models/__init__.py`, adicionar o import (alfabético) e ao `__all__`:
```python
from backend.infra.db.models.export_config import ExportConfig
```
e `"ExportConfig"` no `__all__`.

- [ ] **Step 3: Migração**

`migrations/versions/0027_export_config.py` (última revisão é `0026_contabil_v2`):

```python
"""export_config (data lake export)

Revision ID: 0027_export_config
Revises: 0026_contabil_v2
Create Date: 2026-06-17 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0027_export_config"
down_revision: Union[str, Sequence[str], None] = "0026_contabil_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_config",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("destination", sa.String(20), nullable=False, server_default="s3"),
        sa.Column("s3_bucket", sa.String(200)),
        sa.Column("s3_region", sa.String(40)),
        sa.Column("s3_prefix", sa.String(300)),
        sa.Column("s3_access_key_id", sa.String(200)),
        sa.Column("s3_secret_access_key", sa.String(300)),
        sa.Column("databricks_host", sa.String(300)),
        sa.Column("databricks_token", sa.String(300)),
        sa.Column("databricks_volume_path", sa.String(400)),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_status", sa.String(20)),
        sa.Column("last_run_detail", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("export_config")
```

- [ ] **Step 4: Cleanup nos testes**

Em `backend/tests/api/conftest.py`: importar `ExportConfig` e adicionar `ExportConfig.__table__` à tupla de limpeza (não tem FK; qualquer posição).

- [ ] **Step 5: Aplicar e verificar**

Run: `docker compose run --rm api alembic upgrade head`
Expected: aplica `0027_export_config` sem erro.

- [ ] **Step 6: Commit**

```bash
git add backend/infra/db/models/export_config.py backend/infra/db/models/__init__.py migrations/versions/0027_export_config.py backend/tests/api/conftest.py
git commit -m "feat(export): migração + model ExportConfig"
```

---

## Task 2: Deps + `table_to_parquet`

**Files:**
- Modify: `pyproject.toml`
- Create: `backend/core/export/__init__.py`, `backend/core/export/serialize.py`
- Test: `backend/tests/core/test_export_serialize.py`

- [ ] **Step 1: Deps + rebuild**

Em `pyproject.toml`, adicionar `"pyarrow>=17"` e `"boto3>=1.34"` às dependências.
Run: `docker compose build api`
Run: `docker compose run --rm api python -c "import pyarrow, boto3; print(pyarrow.__version__, boto3.__version__)"`
Expected: imprime as versões.

- [ ] **Step 2: Teste**

`backend/tests/core/test_export_serialize.py`:

```python
import io
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pyarrow.parquet as pq

from backend.core.export.serialize import table_to_parquet


def test_parquet_roundtrip_with_types():
    rows = [
        {"id": UUID("11111111-1111-1111-1111-111111111111"), "preco": Decimal("12.34"),
         "criado": datetime(2026, 6, 1, tzinfo=timezone.utc), "meta": {"a": 1}, "n": None, "ok": True},
    ]
    cols = ["id", "preco", "criado", "meta", "n", "ok"]
    data = table_to_parquet(rows, cols)
    table = pq.read_table(io.BytesIO(data))
    assert table.column_names == cols
    rec = table.to_pylist()[0]
    assert rec["id"] == "11111111-1111-1111-1111-111111111111"
    assert rec["preco"] == "12.34"           # Decimal -> str
    assert rec["meta"] == '{"a": 1}'          # JSON string
    assert rec["ok"] is True


def test_empty_table_keeps_columns():
    data = table_to_parquet([], ["id", "nome"])
    table = pq.read_table(io.BytesIO(data))
    assert table.column_names == ["id", "nome"]
    assert table.num_rows == 0
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_serialize.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 4: Implementar**

`backend/core/export/__init__.py`: vazio.

`backend/core/export/serialize.py`:

```python
import io
import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

import pyarrow as pa
import pyarrow.parquet as pq


def _coerce(v):
    if v is None:
        return None
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str, ensure_ascii=False)
    if isinstance(v, (datetime, date, bool, int, float, str)):
        return v
    return str(v)


def table_to_parquet(rows: list[dict], columns: list[str]) -> bytes:
    """Serializa linhas (list[dict]) em Parquet, com coerção de tipos.

    Decimais/UUID viram str (sem perda); dict/list (JSONB) viram JSON string;
    datetime/bool/int/float/str ficam nativos. Colunas vazias preservam o schema.
    """
    data = {c: [_coerce(r.get(c)) for r in rows] for c in columns}
    table = pa.table(data)
    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()
```

- [ ] **Step 5: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_serialize.py -q`
Expected: PASS (2).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml backend/core/export/__init__.py backend/core/export/serialize.py backend/tests/core/test_export_serialize.py
git commit -m "feat(export): pyarrow/boto3 + table_to_parquet"
```

---

## Task 3: Registry de entidades

**Files:**
- Create: `backend/core/export/entities.py`
- Test: `backend/tests/core/test_export_entities.py`

- [ ] **Step 1: Teste**

`backend/tests/core/test_export_entities.py`:

```python
from backend.core.export.entities import EXPORT_ENTITIES, columns_for


def test_secrets_excluded_and_users_has_no_hash():
    names = {name for name, _model, _ex in EXPORT_ENTITIES}
    assert "settings" not in names
    assert "export_config" not in names
    assert "quotes" in names and "sales" in names and "users" in names
    users = next(e for e in EXPORT_ENTITIES if e[0] == "users")
    assert "password_hash" not in columns_for(users)
    assert "email" in columns_for(users)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_entities.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

`backend/core/export/entities.py`:

```python
from backend.infra.db.models import (
    Asset, CalibrationInsight, Client, DataSourceRun, Expense, KeywordIdea,
    KeywordObservation, LLMDigest, LLMSuggestion, MaterialConsumption, MaterialVersion,
    ProductionEvent, ProductionSuggestion, Quote, QuoteItem, QuoteService, Sale,
    Service, Spool, User, WatcherInboxFile,
)

# (nome no destino, model, colunas excluídas). Segredos (settings, export_config)
# ficam de fora; users sai sem password_hash.
EXPORT_ENTITIES: list[tuple[str, type, set[str]]] = [
    ("quotes", Quote, set()),
    ("quote_items", QuoteItem, set()),
    ("quote_services", QuoteService, set()),
    ("sales", Sale, set()),
    ("expenses", Expense, set()),
    ("material_versions", MaterialVersion, set()),
    ("material_consumptions", MaterialConsumption, set()),
    ("spools", Spool, set()),
    ("clients", Client, set()),
    ("services", Service, set()),
    ("production_events", ProductionEvent, set()),
    ("production_suggestions", ProductionSuggestion, set()),
    ("calibration_insights", CalibrationInsight, set()),
    ("assets", Asset, set()),
    ("data_source_runs", DataSourceRun, set()),
    ("keyword_ideas", KeywordIdea, set()),
    ("keyword_observations", KeywordObservation, set()),
    ("llm_digests", LLMDigest, set()),
    ("llm_suggestions", LLMSuggestion, set()),
    ("watcher_inbox_files", WatcherInboxFile, set()),
    ("users", User, {"password_hash"}),
]


def columns_for(entry: tuple[str, type, set[str]]) -> list[str]:
    _name, model, excluded = entry
    return [c.name for c in model.__table__.columns if c.name not in excluded]
```

NOTA: `ProductionEvent` tem coluna `embedding` (pgvector) — confirmar que `_coerce`/pyarrow lida com o valor que o ORM retorna (lista de floats vira JSON string via o ramo dict/list? não — é list, então vira JSON string; ok). Se o valor vier como objeto pgvector não-serializável, o `_coerce` cai no `str(v)` final. O teste do runner (Task 5) cobre entidades reais.

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_entities.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/export/entities.py backend/tests/core/test_export_entities.py
git commit -m "feat(export): registry de entidades (segredos fora, users sem hash)"
```

---

## Task 4: Destinos S3 + Databricks

**Files:**
- Create: `backend/core/export/destinations.py`
- Test: `backend/tests/core/test_export_destinations.py`

- [ ] **Step 1: Teste**

`backend/tests/core/test_export_destinations.py`:

```python
import backend.core.export.destinations as d
from backend.core.export.destinations import (
    DatabricksDestination, S3Destination, build_destination,
)


def test_s3_put_calls_put_object(monkeypatch):
    calls = {}

    class FakeClient:
        def put_object(self, **kw):
            calls.update(kw)

    monkeypatch.setattr(d.boto3, "client", lambda *a, **k: FakeClient())
    dest = S3Destination(bucket="b", region="us-east-1", prefix="pre",
                         access_key="ak", secret="sk")
    dest.put("20260617T000000Z/quotes.parquet", b"abc")
    assert calls["Bucket"] == "b"
    assert calls["Key"] == "pre/20260617T000000Z/quotes.parquet"
    assert calls["Body"] == b"abc"


def test_databricks_put_uses_files_api(monkeypatch):
    seen = {}

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass

    def fake_put(url, headers=None, content=None, timeout=None):
        seen["url"] = url; seen["headers"] = headers; seen["content"] = content
        return FakeResp()

    monkeypatch.setattr(d.httpx, "put", fake_put)
    dest = DatabricksDestination(host="https://x.databricks.com",
                                 token="tok", volume_path="/Volumes/c/s/v/base")
    dest.put("run/quotes.parquet", b"abc")
    assert seen["url"] == "https://x.databricks.com/api/2.0/fs/files/Volumes/c/s/v/base/run/quotes.parquet?overwrite=true"
    assert seen["headers"]["Authorization"] == "Bearer tok"
    assert seen["content"] == b"abc"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_destinations.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

`backend/core/export/destinations.py`:

```python
from typing import Protocol

import boto3
import httpx


class Destination(Protocol):
    def put(self, rel_path: str, data: bytes) -> None: ...


class S3Destination:
    def __init__(self, bucket: str, region: str | None, prefix: str | None,
                 access_key: str | None, secret: str | None) -> None:
        self.bucket = bucket
        self.region = region
        self.prefix = (prefix or "").rstrip("/")
        self.access_key = access_key
        self.secret = secret

    def put(self, rel_path: str, data: bytes) -> None:
        client = boto3.client(
            "s3", region_name=self.region,
            aws_access_key_id=self.access_key, aws_secret_access_key=self.secret,
        )
        key = f"{self.prefix}/{rel_path}" if self.prefix else rel_path
        client.put_object(Bucket=self.bucket, Key=key, Body=data)


class DatabricksDestination:
    def __init__(self, host: str, token: str, volume_path: str) -> None:
        self.host = host.rstrip("/")
        self.token = token
        self.volume_path = volume_path.rstrip("/")

    def put(self, rel_path: str, data: bytes) -> None:
        url = f"{self.host}/api/2.0/fs/files{self.volume_path}/{rel_path}?overwrite=true"
        resp = httpx.put(url, headers={"Authorization": f"Bearer {self.token}"},
                         content=data, timeout=60)
        resp.raise_for_status()


def build_destination(cfg) -> Destination:
    if cfg.destination == "databricks":
        if not (cfg.databricks_host and cfg.databricks_token and cfg.databricks_volume_path):
            raise ValueError("databricks destination não configurado (host/token/volume)")
        return DatabricksDestination(cfg.databricks_host, cfg.databricks_token, cfg.databricks_volume_path)
    if cfg.destination == "s3":
        if not cfg.s3_bucket:
            raise ValueError("s3 destination não configurado (bucket)")
        return S3Destination(cfg.s3_bucket, cfg.s3_region, cfg.s3_prefix,
                             cfg.s3_access_key_id, cfg.s3_secret_access_key)
    raise ValueError(f"destino desconhecido: {cfg.destination}")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_destinations.py -q`
Expected: PASS (2).

- [ ] **Step 5: Commit**

```bash
git add backend/core/export/destinations.py backend/tests/core/test_export_destinations.py
git commit -m "feat(export): destinos S3 e Databricks + build_destination"
```

---

## Task 5: Runner (`run_export` + `execute_export`)

**Files:**
- Create: `backend/core/export/runner.py`
- Test: `backend/tests/core/test_export_runner.py`

- [ ] **Step 1: Teste**

`backend/tests/core/test_export_runner.py`:

```python
from decimal import Decimal

import pytest

from backend.core.export.runner import execute_export, run_export
import backend.core.export.runner as runner_mod
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import ExportConfig, Quote, User


class FakeDestination:
    def __init__(self):
        self.puts = {}

    def put(self, rel_path, data):
        self.puts[rel_path] = data


@pytest.mark.asyncio
async def test_run_export_one_file_per_entity():
    async with session_module.SessionFactory() as s:
        u = User(name="u", email="exp@t.com", password_hash="x")
        s.add(u); await s.commit()
        s.add(Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                    status=QuoteStatus.APROVADO.value, markup_pct=Decimal("0"), min_charge=Decimal("0")))
        await s.commit()

    dest = FakeDestination()
    async with session_module.SessionFactory() as s:
        summary = await run_export(s, dest)

    # um arquivo por entidade, todos sob a mesma pasta run_ts
    assert any(p.endswith("/quotes.parquet") for p in dest.puts)
    assert any(p.endswith("/users.parquet") for p in dest.puts)
    run_ts = summary["run_ts"]
    assert all(p.startswith(f"{run_ts}/") for p in dest.puts)
    assert summary["counts"]["quotes"] >= 1


@pytest.mark.asyncio
async def test_execute_export_records_status(monkeypatch):
    async with session_module.SessionFactory() as s:
        await s.merge(ExportConfig(id=1, destination="s3", s3_bucket="b"))
        await s.commit()

    dest = FakeDestination()
    monkeypatch.setattr(runner_mod, "build_destination", lambda cfg: dest)

    async with session_module.SessionFactory() as s:
        res = await execute_export(s)
    assert res["ok"] is True

    async with session_module.SessionFactory() as s:
        cfg = await s.get(ExportConfig, 1)
        assert cfg.last_run_status == "ok"
        assert cfg.last_run_at is not None


@pytest.mark.asyncio
async def test_execute_export_error_path(monkeypatch):
    async with session_module.SessionFactory() as s:
        await s.merge(ExportConfig(id=1, destination="s3", s3_bucket="b"))
        await s.commit()

    def boom(cfg):
        raise ValueError("sem credencial")
    monkeypatch.setattr(runner_mod, "build_destination", boom)

    async with session_module.SessionFactory() as s:
        res = await execute_export(s)
    assert res["ok"] is False
    assert "sem credencial" in res["detail"]
    async with session_module.SessionFactory() as s:
        cfg = await s.get(ExportConfig, 1)
        assert cfg.last_run_status == "error"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_runner.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

`backend/core/export/runner.py`:

```python
import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.export.destinations import Destination, build_destination
from backend.core.export.entities import EXPORT_ENTITIES, columns_for
from backend.core.export.serialize import table_to_parquet
from backend.infra.db.models import ExportConfig


async def run_export(session: AsyncSession, destination: Destination) -> dict:
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    counts: dict[str, int] = {}
    for entry in EXPORT_ENTITIES:
        name, model, _excluded = entry
        cols = columns_for(entry)
        objs = (await session.execute(select(model))).scalars().all()
        rows = [{c: getattr(o, c) for c in cols} for o in objs]
        data = table_to_parquet(rows, cols)
        await asyncio.to_thread(destination.put, f"{run_ts}/{name}.parquet", data)
        counts[name] = len(rows)
    return {"run_ts": run_ts, "counts": counts}


async def execute_export(session: AsyncSession) -> dict:
    """Carrega a config, monta o destino, roda o export e grava last_run_*."""
    cfg = await session.get(ExportConfig, 1)
    if cfg is None:
        cfg = ExportConfig(id=1)
        session.add(cfg)
        await session.commit()
    try:
        dest = build_destination(cfg)
        summary = await run_export(session, dest)
        cfg.last_run_at = datetime.now(timezone.utc)
        cfg.last_run_status = "ok"
        cfg.last_run_detail = json.dumps(summary["counts"])
        await session.commit()
        return {"ok": True, **summary}
    except Exception as exc:  # destino/credencial/serialização
        cfg.last_run_at = datetime.now(timezone.utc)
        cfg.last_run_status = "error"
        cfg.last_run_detail = str(exc)
        await session.commit()
        return {"ok": False, "detail": str(exc)}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_runner.py -q`
Expected: PASS (3). Se uma entidade real falhar na serialização (ex.: `embedding` pgvector), ajustar `_coerce` (já tem fallback `str(v)`) — investigar o valor real e cobrir, sem afrouxar o teste.

- [ ] **Step 5: Commit**

```bash
git add backend/core/export/runner.py backend/tests/core/test_export_runner.py
git commit -m "feat(export): runner run_export + execute_export"
```

---

## Task 6: API `/config/export`

**Files:**
- Modify: `backend/api/schemas/config.py`, `backend/api/routes/config.py`
- Test: `backend/tests/api/test_export_config.py`

- [ ] **Step 1: Teste**

`backend/tests/api/test_export_config.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_export_config_get_put_mask(auth_client):
    # default
    r = await auth_client.get("/config/export")
    assert r.status_code == 200, r.text
    # configura s3 com segredo
    r = await auth_client.put("/config/export", json={
        "destination": "s3", "s3_bucket": "meu-bucket", "s3_region": "us-east-1",
        "s3_access_key_id": "AKIA", "s3_secret_access_key": "supersecret", "enabled": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["destination"] == "s3"
    assert body["s3_bucket"] == "meu-bucket"
    assert body["enabled"] is True
    # segredo mascarado (não retorna o valor cru)
    assert body["s3_secret_access_key_preview"] != "supersecret"
    assert body["s3_secret_configured"] is True


@pytest.mark.asyncio
async def test_export_run_force(auth_client, monkeypatch):
    import backend.api.routes.config as cfg_routes

    async def fake_execute(session):
        return {"ok": True, "run_ts": "20260617T000000Z", "counts": {"quotes": 0}}
    monkeypatch.setattr(cfg_routes, "execute_export", fake_execute)

    r = await auth_client.post("/config/export/run")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_export_config.py -q`
Expected: FAIL — 404.

- [ ] **Step 3: Schemas**

Em `backend/api/schemas/config.py`, adicionar (o módulo já tem `_mask`-style no route, aqui só os modelos):

```python
class ExportConfigOut(BaseModel):
    enabled: bool
    destination: str
    s3_bucket: str | None
    s3_region: str | None
    s3_prefix: str | None
    s3_access_key_id: str | None
    s3_secret_configured: bool
    s3_secret_access_key_preview: str | None
    databricks_host: str | None
    databricks_volume_path: str | None
    databricks_token_configured: bool
    databricks_token_preview: str | None
    last_run_at: str | None
    last_run_status: str | None
    last_run_detail: str | None


class ExportConfigUpdate(BaseModel):
    enabled: bool | None = None
    destination: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_prefix: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    databricks_host: str | None = None
    databricks_token: str | None = None
    databricks_volume_path: str | None = None
```

- [ ] **Step 4: Rotas**

Em `backend/api/routes/config.py`, importar no topo:
```python
from backend.api.schemas.config import ExportConfigOut, ExportConfigUpdate
from backend.core.export.runner import execute_export
from backend.infra.db.models import ExportConfig
```
Helpers + rotas (usa o `_mask` já existente no módulo):

```python
async def _get_export_cfg(session: AsyncSession) -> ExportConfig:
    cfg = await session.get(ExportConfig, 1)
    if cfg is None:
        cfg = ExportConfig(id=1)
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


def _export_out(c: ExportConfig) -> ExportConfigOut:
    return ExportConfigOut(
        enabled=c.enabled, destination=c.destination,
        s3_bucket=c.s3_bucket, s3_region=c.s3_region, s3_prefix=c.s3_prefix,
        s3_access_key_id=c.s3_access_key_id,
        s3_secret_configured=bool(c.s3_secret_access_key),
        s3_secret_access_key_preview=_mask(c.s3_secret_access_key),
        databricks_host=c.databricks_host, databricks_volume_path=c.databricks_volume_path,
        databricks_token_configured=bool(c.databricks_token),
        databricks_token_preview=_mask(c.databricks_token),
        last_run_at=c.last_run_at.isoformat() if c.last_run_at else None,
        last_run_status=c.last_run_status, last_run_detail=c.last_run_detail,
    )


@router.get("/export", response_model=ExportConfigOut)
async def get_export_config(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    return _export_out(await _get_export_cfg(session))


@router.put("/export", response_model=ExportConfigOut)
async def put_export_config(payload: ExportConfigUpdate, _: User = Depends(require_user),
                            session: AsyncSession = Depends(db_session)):
    c = await _get_export_cfg(session)
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k in ("s3_secret_access_key", "databricks_token"):
            # segredo só é sobrescrito quando vier um valor; vazio = não altera
            if v:
                setattr(c, k, v)
        else:
            setattr(c, k, v if v != "" else None)
    await session.commit(); await session.refresh(c)
    return _export_out(c)


@router.post("/export/run")
async def run_export_now(_: User = Depends(require_user), session: AsyncSession = Depends(db_session)):
    return await execute_export(session)
```

(`User`, `require_user`, `db_session`, `AsyncSession`, `_mask` já estão importados no módulo.)

- [ ] **Step 5: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_export_config.py -q`
Expected: PASS (2).

- [ ] **Step 6: Commit**

```bash
git add backend/api/schemas/config.py backend/api/routes/config.py backend/tests/api/test_export_config.py
git commit -m "feat(export): API /config/export (get/put mascarado + run)"
```

---

## Task 7: Scheduler diário

**Files:**
- Create: `backend/infra/scheduler/export.py`
- Modify: `backend/app.py`
- Test: `backend/tests/core/test_export_scheduler.py`

- [ ] **Step 1: Teste**

`backend/tests/core/test_export_scheduler.py`:

```python
import pytest

import backend.infra.scheduler.export as sched
from backend.infra.db import session as session_module
from backend.infra.db.models import ExportConfig


@pytest.mark.asyncio
async def test_export_once_respects_enabled(monkeypatch):
    calls = {"n": 0}

    async def fake_execute(session):
        calls["n"] += 1
        return {"ok": True}
    monkeypatch.setattr(sched, "execute_export", fake_execute)

    # desabilitado -> não roda
    async with session_module.SessionFactory() as s:
        await s.merge(ExportConfig(id=1, enabled=False, destination="s3", s3_bucket="b"))
        await s.commit()
    await sched.export_once()
    assert calls["n"] == 0

    # habilitado -> roda
    async with session_module.SessionFactory() as s:
        await s.merge(ExportConfig(id=1, enabled=True, destination="s3", s3_bucket="b"))
        await s.commit()
    await sched.export_once()
    assert calls["n"] == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_scheduler.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar**

`backend/infra/scheduler/export.py`:

```python
import asyncio

from backend.core.export.runner import execute_export
from backend.infra.db.models import ExportConfig
from backend.infra.db.session import SessionFactory

ONE_DAY_SECONDS = 24 * 60 * 60


async def export_once() -> None:
    """Roda o export se o envio diário estiver habilitado."""
    async with SessionFactory() as session:
        cfg = await session.get(ExportConfig, 1)
        if cfg is None or not cfg.enabled:
            return
    async with SessionFactory() as session:
        await execute_export(session)


async def run_forever() -> None:
    while True:
        try:
            await export_once()
        except Exception:
            pass
        await asyncio.sleep(ONE_DAY_SECONDS)


def start_background_task() -> asyncio.Task:
    return asyncio.create_task(run_forever())
```

NOTA: confirmar que `backend.infra.db.session` exporta `SessionFactory` (os outros schedulers usam o mesmo). Se o nome diferir, usar o mesmo que `trends.py` importa.

- [ ] **Step 4: Registrar no app**

Em `backend/app.py`, no `lifespan`, junto dos outros `start_background_task` (sempre inicia o loop; ele se auto-gateia no `enabled` a cada ciclo):
```python
        from backend.infra.scheduler.export import start_background_task as start_export
        app.state.export_task = start_export()
        tasks.append(app.state.export_task)
```
(colocar fora do `if s.trends_enabled:` — o gate do export é interno, por ciclo.)

- [ ] **Step 5: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_export_scheduler.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/infra/scheduler/export.py backend/app.py backend/tests/core/test_export_scheduler.py
git commit -m "feat(export): scheduler diário (gateado por enabled)"
```

---

## Task 8: Frontend — seção Data Lake na Integrações

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/routes/config/+page.svelte`

- [ ] **Step 1: Tipos**

Em `frontend/src/lib/types.ts`, adicionar:
```typescript
export type ExportConfig = {
  enabled: boolean;
  destination: "s3" | "databricks";
  s3_bucket: string | null;
  s3_region: string | null;
  s3_prefix: string | null;
  s3_access_key_id: string | null;
  s3_secret_configured: boolean;
  s3_secret_access_key_preview: string | null;
  databricks_host: string | null;
  databricks_volume_path: string | null;
  databricks_token_configured: boolean;
  databricks_token_preview: string | null;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_detail: string | null;
};
```

- [ ] **Step 2: Seção na página**

Em `frontend/src/routes/config/+page.svelte` (estudar o arquivo: ele já faz `api` GET/PUT em `/config/providers` e tem campos com máscara). Adicionar uma seção "Data Lake / Export" que:
- carrega `api<ExportConfig>("/config/export")` no `onMount` (junto do load existente);
- mostra um seletor de destino (`s3` | `databricks`) e, conforme o destino, os campos respectivos (bucket/region/prefix/access key/secret pra S3; host/token/volume pra Databricks) — segredos com placeholder do `*_preview` e campo vazio = não altera;
- um toggle "Ativar envio diário" (`enabled`);
- botão "Salvar" → `PUT /config/export` com os campos preenchidos (segredo vazio não sobrescreve);
- botão "Exportar agora" → `POST /config/export/run`, mostrando o resultado (`ok`/`detail`) e atualizando o status;
- exibe `last_run_at` / `last_run_status` / `last_run_detail`.
Seguir o estilo/CSS dos blocos de provider já existentes na página. Sem `any`.

- [ ] **Step 3: Check**

Run: `cd frontend && npm run check`
Expected: sem erros novos (só os pré-existentes de library/spools).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/routes/config/+page.svelte
git commit -m "feat(export): seção Data Lake na aba Integrações"
```

---

## Task 9: Verificação

- [ ] **Step 1:** `docker compose run --rm api pytest backend/tests -q` → tudo PASS.
- [ ] **Step 2:** `cd frontend && npm run check` → sem erros novos.
- [ ] **Step 3:** `docker compose run --rm api ruff check backend/core/export backend/infra/scheduler/export.py backend/api/routes/config.py` → sem erros novos (E702 de estilo tolerado).

---

## Notas

- **Segredos em texto** na tabela (mesmo nível dos tokens meli/reddit). Criptografia at-rest fica pra evolução.
- **boto3/httpx síncronos** rodam via `asyncio.to_thread` (S3) / chamada direta (Databricks `httpx.put` é síncrono — envolver em `asyncio.to_thread` se o bloqueio incomodar; na escala atual, ok).
- **`embedding` (pgvector)** em `production_events`: `_coerce` tem fallback `str(v)`; o teste do runner exercita entidades reais — se quebrar, tratar o valor pgvector explicitamente.
- **Carrega tabela inteira em memória** por entidade (escala atual ok).
