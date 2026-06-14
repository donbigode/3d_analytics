# Produção — Fase B (IA: embeddings + sugestões) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sobre os `production_events` da Fase A, gerar embeddings das falhas e, sob demanda, uma sugestão de IA ("o que vigiar") por material — cacheada para não gastar token à toa — exibida na aba Insights.

**Architecture:** Um módulo `backend/core/production/suggestions.py` com a lógica pura (compor texto da falha, preencher embeddings via `embed()`, agrupar/deduplicar por similaridade com `cosine_similarity`, e chamar o LLM uma única vez via `call_json` para produzir sugestões por material). O resultado é persistido numa tabela de cache `production_suggestions` (padrão `LLMDigest`). Dois endpoints em `/insights`: `POST .../generate` (gera+cacheia, sob demanda) e `GET ...` (lê cache + flag de "desatualizado"). Frontend: botão "Gerar sugestões" na seção de produção do Insights.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, pgvector (coluna já existe), `backend.core.trends.embeddings` (e5/384-d), `backend.core.llm_features.runner` (cadeia de providers). Testes: pytest + httpx em container (`docker compose run --rm api pytest ...`), com `embed` e `call_json` monkeypatchados (sem API real / sem baixar modelo).

**Referência do spec:** `docs/superpowers/specs/2026-06-14-producao-eventos-falha-design.md` (§6).
**Decisão de custo (YAGNI):** em vez de parsing LLM por evento (`llm_tags`), uma única chamada de sugestão por geração; a coluna `llm_tags` permanece para uso futuro.

---

## Arquivos (mapa)

- `backend/core/production/__init__.py` — **criar** (pacote).
- `backend/core/production/suggestions.py` — **criar**: `failure_event_text`, `fill_failure_embeddings`, `gather_failures`, `generate_suggestions`.
- `backend/infra/db/models/production_suggestion.py` — **criar** modelo de cache.
- `backend/infra/db/models/__init__.py` — exportar `ProductionSuggestion`.
- `migrations/versions/0024_production_suggestions.py` — **criar** tabela de cache.
- `backend/api/routes/insights.py` — endpoints `POST /insights/production-suggestions/generate` e `GET /insights/production-suggestions`.
- `frontend/src/lib/types.ts` — tipos `ProductionSuggestion`, `ProductionSuggestionsOut`.
- `frontend/src/routes/insights/+page.svelte` — botão "Gerar sugestões" + render.
- Testes: `backend/tests/api/test_production_suggestions.py`, `backend/tests/core/test_suggestions_logic.py`.

---

## Task 1: Tabela de cache `production_suggestions`

**Files:**
- Create: `backend/infra/db/models/production_suggestion.py`
- Modify: `backend/infra/db/models/__init__.py`
- Create: `migrations/versions/0024_production_suggestions.py`
- Test: `backend/tests/api/test_production_suggestions.py`

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/api/test_production_suggestions.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_production_suggestion_table_exists(auth_client):
    from backend.infra.db.models import ProductionSuggestion
    assert ProductionSuggestion.__tablename__ == "production_suggestions"
    cols = set(ProductionSuggestion.__table__.columns.keys())
    assert {"id", "body", "provider", "source_count", "generated_at"} <= cols
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_suggestions.py::test_production_suggestion_table_exists -q`
Expected: FAIL — `ImportError: cannot import name 'ProductionSuggestion'`.

- [ ] **Step 3: Criar o modelo**

`backend/infra/db/models/production_suggestion.py`:

```python
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class ProductionSuggestion(Base):
    """Cache da última geração de sugestões de produção (padrão LLMDigest:
    gera sob demanda, persiste, relê sem gastar token). `source_count` guarda
    quantos eventos existiam na geração, para sinalizar 'desatualizado'."""
    __tablename__ = "production_suggestions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    body: Mapped[list | dict] = mapped_column(JSONB, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 4: Exportar no `__init__`**

Em `backend/infra/db/models/__init__.py` adicionar a import (em ordem) e ao `__all__`:

```python
from backend.infra.db.models.production_suggestion import ProductionSuggestion
```
e `"ProductionSuggestion",` na lista `__all__`.

- [ ] **Step 5: Criar a migração**

`migrations/versions/0024_production_suggestions.py`:

```python
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "0024_production_suggestions"
down_revision: Union[str, Sequence[str], None] = "0023_production_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "production_suggestions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("body", JSONB, nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("source_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("generated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("production_suggestions")
```

- [ ] **Step 6: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_suggestions.py::test_production_suggestion_table_exists -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/infra/db/models/production_suggestion.py backend/infra/db/models/__init__.py migrations/versions/0024_production_suggestions.py backend/tests/api/test_production_suggestions.py
git commit -m "feat(db): tabela production_suggestions (cache) + migração 0024"
```

---

## Task 2: Lógica — texto da falha + preencher embeddings

**Files:**
- Create: `backend/core/production/__init__.py` (vazio)
- Create: `backend/core/production/suggestions.py`
- Test: `backend/tests/core/test_suggestions_logic.py`

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/core/test_suggestions_logic.py`:

```python
from backend.core.production.suggestions import failure_event_text


class _Ev:
    def __init__(self, desc, ctx):
        self.failure_description = desc
        self.context = ctx


def test_failure_event_text_composes_material_and_description():
    ev = _Ev("descolou da mesa", [
        {"material_type": "PETG", "color": "Transparente", "manufacturer": "3D Lab",
         "filament_m": 12.5, "time_s": 7200, "is_multi_color": False},
    ])
    text = failure_event_text(ev)
    assert "PETG" in text
    assert "Transparente" in text
    assert "descolou da mesa" in text
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/core/test_suggestions_logic.py::test_failure_event_text_composes_material_and_description -q`
Expected: FAIL — módulo não existe.

- [ ] **Step 3: Criar o pacote e o módulo (parte 1)**

`backend/core/production/__init__.py`: arquivo vazio.

`backend/core/production/suggestions.py`:

```python
"""Sugestões de produção (Fase B): embeddings das falhas + uma chamada LLM
sob demanda que resume 'o que vigiar' por material. Resultado cacheado."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.llm_features.runner import LLMUnavailable, call_json
from backend.core.models import ProductionOutcome
from backend.core.trends.embeddings import cosine_similarity, embed
from backend.infra.db.models import ProductionEvent, ProductionSuggestion


def failure_event_text(ev: Any) -> str:
    """Texto compacto da falha para embedding e prompt."""
    parts: list[str] = []
    for piece in (ev.context or []):
        p = piece or {}
        mat = " ".join(
            str(x) for x in [p.get("material_type"), p.get("color"), p.get("manufacturer")] if x
        )
        chars = []
        if p.get("is_multi_color"):
            chars.append("multicor")
        if p.get("filament_m"):
            chars.append(f"{p['filament_m']}m")
        if p.get("time_s"):
            chars.append(f"{round(float(p['time_s']) / 3600, 1)}h")
        seg = mat
        if chars:
            seg += " (" + ", ".join(chars) + ")"
        if seg.strip():
            parts.append(seg.strip())
    ctx = "; ".join(parts)
    desc = (ev.failure_description or "").strip()
    return f"{ctx}: {desc}" if ctx else desc
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/core/test_suggestions_logic.py::test_failure_event_text_composes_material_and_description -q`
Expected: PASS.

- [ ] **Step 5: Teste do preenchimento de embeddings (monkeypatch `embed`)**

Adicionar em `test_production_suggestions.py` (é async + DB, então fica no arquivo de API):

```python
@pytest.mark.asyncio
async def test_fill_failure_embeddings_sets_vectors(auth_client, monkeypatch):
    from backend.tests.api.test_production_flow import (
        _seed_material, _spool, _approved_commercial)
    from backend.core.production import suggestions as S
    from backend.infra.db.session import SessionFactory
    from backend.infra.db.models import ProductionEvent
    from sqlalchemy import select

    async def fake_embed(texts):
        return [[0.1] * 384 for _ in texts]
    monkeypatch.setattr(S, "embed", fake_embed)

    await _seed_material(auth_client); sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    await auth_client.post(f"/quotes/{qid}/transitions/fail",
        json={"failure_description": "warping", "attempts": 1})

    async with SessionFactory() as session:
        n = await S.fill_failure_embeddings(session)
        assert n == 1
        ev = (await session.execute(
            select(ProductionEvent).where(ProductionEvent.outcome == "failure")
        )).scalars().first()
        assert ev.embedding is not None
        assert len(list(ev.embedding)) == 384
```

- [ ] **Step 6: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_suggestions.py::test_fill_failure_embeddings_sets_vectors -q`
Expected: FAIL — `fill_failure_embeddings` não existe.

- [ ] **Step 7: Implementar `fill_failure_embeddings`**

Adicionar em `backend/core/production/suggestions.py`:

```python
async def fill_failure_embeddings(session: AsyncSession) -> int:
    """Embeda falhas que ainda não têm vetor. Retorna quantas preencheu."""
    rows = (await session.execute(
        select(ProductionEvent).where(
            ProductionEvent.outcome == ProductionOutcome.FAILURE,
            ProductionEvent.embedding.is_(None),
        )
    )).scalars().all()
    pending = [(e, failure_event_text(e)) for e in rows]
    pending = [(e, t) for e, t in pending if t]
    if not pending:
        return 0
    vectors = await embed([t for _, t in pending])
    for (e, _), vec in zip(pending, vectors):
        e.embedding = vec
    await session.commit()
    return len(pending)
```

- [ ] **Step 8: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_suggestions.py::test_fill_failure_embeddings_sets_vectors -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/core/production/ backend/tests/core/test_suggestions_logic.py backend/tests/api/test_production_suggestions.py
git commit -m "feat(production): texto da falha + preenchimento de embeddings"
```

---

## Task 3: Geração de sugestões (1 chamada LLM, cacheada)

**Files:**
- Modify: `backend/core/production/suggestions.py`
- Test: `backend/tests/api/test_production_suggestions.py`

- [ ] **Step 1: Escrever o teste que falha (monkeypatch `embed` e `call_json`)**

```python
@pytest.mark.asyncio
async def test_generate_suggestions_caches_llm_output(auth_client, monkeypatch):
    from backend.tests.api.test_production_flow import (
        _seed_material, _spool, _approved_commercial)
    from backend.core.production import suggestions as S
    from backend.infra.db.session import SessionFactory

    async def fake_embed(texts):
        return [[0.1] * 384 for _ in texts]

    async def fake_call_json(session, *, system, user, max_tokens=800):
        # devolve a estrutura que o gerador espera
        return {"suggestions": [
            {"material_type": "PLA", "advice": "reduza velocidade da 1a camada"}
        ]}

    monkeypatch.setattr(S, "embed", fake_embed)
    monkeypatch.setattr(S, "call_json", fake_call_json)

    await _seed_material(auth_client); sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    await auth_client.post(f"/quotes/{qid}/transitions/fail",
        json={"failure_description": "warping nos cantos", "attempts": 1})

    async with SessionFactory() as session:
        out = await S.generate_suggestions(session)
        assert out["source_count"] == 1
        assert out["suggestions"][0]["material_type"] == "PLA"
        # persistiu no cache
        from backend.infra.db.models import ProductionSuggestion
        from sqlalchemy import select
        cached = (await session.execute(select(ProductionSuggestion))).scalars().all()
        assert len(cached) == 1
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_suggestions.py::test_generate_suggestions_caches_llm_output -q`
Expected: FAIL — `generate_suggestions` não existe.

- [ ] **Step 3: Implementar `gather_failures` + `generate_suggestions`**

Adicionar em `backend/core/production/suggestions.py`:

```python
_SYSTEM = (
    "Você é um especialista em impressão 3D FDM. Recebe uma lista de falhas de "
    "produção agrupadas por material e responde, em português, o que vigiar para "
    "evitar cada tipo de falha. Responda APENAS JSON no formato "
    '{"suggestions": [{"material_type": str, "advice": str}]}. '
    "advice deve ser curto (1-2 frases), prático e específico ao material."
)


async def gather_failures(session: AsyncSession) -> list[dict]:
    """Falhas com texto, deduplicando descrições muito similares (cosine>=0.92)
    quando há embedding, para o prompt ficar compacto."""
    rows = (await session.execute(
        select(ProductionEvent).where(
            ProductionEvent.outcome == ProductionOutcome.FAILURE
        ).order_by(ProductionEvent.created_at.desc())
    )).scalars().all()
    out: list[dict] = []
    seen_vecs: list[list[float]] = []
    for e in rows:
        text = failure_event_text(e)
        if not text:
            continue
        if e.embedding is not None:
            vec = list(e.embedding)
            if any(cosine_similarity(vec, s) >= 0.92 for s in seen_vecs):
                continue
            seen_vecs.append(vec)
        mats = sorted({
            (p or {}).get("material_type") for p in (e.context or [])
            if (p or {}).get("material_type")
        })
        out.append({"materials": mats or ["—"], "text": text,
                    "attempts": e.attempts})
    return out


async def generate_suggestions(session: AsyncSession) -> dict:
    """Embeda pendências, monta prompt e chama o LLM 1x; persiste no cache."""
    await fill_failure_embeddings(session)
    failures = await gather_failures(session)
    if not failures:
        return {"suggestions": [], "source_count": 0, "provider": None}

    lines = []
    for f in failures:
        lines.append(f"- [{', '.join(f['materials'])}] (tentativas={f['attempts']}): {f['text']}")
    user = "Falhas registradas:\n" + "\n".join(lines)

    try:
        parsed = await call_json(session, system=_SYSTEM, user=user, max_tokens=900)
    except LLMUnavailable as exc:
        raise LLMUnavailable(str(exc))

    suggestions = parsed.get("suggestions") or []
    row = ProductionSuggestion(
        body={"suggestions": suggestions},
        provider="llm",
        source_count=len(failures),
    )
    session.add(row)
    await session.commit()
    return {"suggestions": suggestions, "source_count": len(failures), "provider": "llm"}
```

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_suggestions.py::test_generate_suggestions_caches_llm_output -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/core/production/suggestions.py backend/tests/api/test_production_suggestions.py
git commit -m "feat(production): geração de sugestões (1 chamada LLM, cacheada)"
```

---

## Task 4: Endpoints de sugestões em /insights

**Files:**
- Modify: `backend/api/routes/insights.py`
- Test: `backend/tests/api/test_production_suggestions.py`

- [ ] **Step 1: Escrever o teste que falha (endpoints, monkeypatch)**

```python
@pytest.mark.asyncio
async def test_suggestions_endpoints_generate_and_read(auth_client, monkeypatch):
    from backend.tests.api.test_production_flow import (
        _seed_material, _spool, _approved_commercial)
    import backend.api.routes.insights as I

    async def fake_generate(session):
        return {"suggestions": [{"material_type": "PLA", "advice": "x"}],
                "source_count": 1, "provider": "llm"}
    monkeypatch.setattr(I, "generate_suggestions", fake_generate)

    # GET vazio antes de gerar
    r0 = await auth_client.get("/insights/production-suggestions")
    assert r0.status_code == 200, r0.text
    assert r0.json()["suggestions"] == []

    r = await auth_client.post("/insights/production-suggestions/generate")
    assert r.status_code == 200, r.text
    assert r.json()["suggestions"][0]["material_type"] == "PLA"
```

(Observação: o GET lê do cache real; como `fake_generate` não persiste, este teste cobre o POST via stub e o GET-vazio. A persistência real é coberta no Task 3.)

- [ ] **Step 2: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_suggestions.py::test_suggestions_endpoints_generate_and_read -q`
Expected: FAIL — rotas não existem.

- [ ] **Step 3: Implementar os endpoints**

Em `backend/api/routes/insights.py`, importar e adicionar:

```python
from sqlalchemy import desc
from backend.core.llm_features.runner import LLMUnavailable
from backend.core.production.suggestions import generate_suggestions
from backend.infra.db.models import ProductionEvent, ProductionSuggestion  # ProductionEvent pode já estar importado


@router.get("/production-suggestions")
async def production_suggestions(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    row = (await session.execute(
        select(ProductionSuggestion).order_by(desc(ProductionSuggestion.generated_at)).limit(1)
    )).scalars().first()
    total_fail = await session.scalar(
        select(func.count(ProductionEvent.id)).where(ProductionEvent.outcome == "failure")
    ) or 0
    if not row:
        return {"suggestions": [], "generated_at": None, "stale": total_fail > 0,
                "source_count": 0, "current_failures": total_fail}
    body = row.body or {}
    return {
        "suggestions": body.get("suggestions", []),
        "generated_at": row.generated_at.isoformat(),
        "source_count": row.source_count,
        "current_failures": total_fail,
        "stale": total_fail != row.source_count,
    }


@router.post("/production-suggestions/generate")
async def production_suggestions_generate(
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    try:
        return await generate_suggestions(session)
    except LLMUnavailable as exc:
        raise HTTPException(503, f"IA indisponível: {exc}")
```

(Garantir que `HTTPException` está importado de `fastapi` no topo — adicionar se faltar.)

- [ ] **Step 4: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_production_suggestions.py -q`
Expected: PASS (todos do arquivo).

- [ ] **Step 5: Suíte inteira**

Run: `docker compose run --rm api pytest -q`
Expected: tudo PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routes/insights.py backend/tests/api/test_production_suggestions.py
git commit -m "feat(insights): endpoints de sugestões de produção (gerar sob demanda + ler cache)"
```

---

## Task 5: Frontend — botão "Gerar sugestões" + render no Insights

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/routes/insights/+page.svelte`

- [ ] **Step 1: Tipos**

Em `frontend/src/lib/types.ts`:

```ts
export type ProductionSuggestion = { material_type: string; advice: string };
export type ProductionSuggestionsOut = {
  suggestions: ProductionSuggestion[];
  generated_at: string | null;
  source_count: number;
  current_failures: number;
  stale: boolean;
};
```

- [ ] **Step 2: Estado + carregamento no Insights**

Em `frontend/src/routes/insights/+page.svelte` (script): importar o tipo, adicionar estado e carregar o cache no `loadOverview`:

```ts
  let suggestions: ProductionSuggestionsOut | null = null;
  let generatingSuggestions = false;
  let suggestionsError = "";

  async function loadSuggestions() {
    try {
      suggestions = await api<ProductionSuggestionsOut>("/insights/production-suggestions");
    } catch (err) {
      handleApiError(err);
    }
  }

  async function generateSuggestions() {
    generatingSuggestions = true;
    suggestionsError = "";
    try {
      await api("/insights/production-suggestions/generate", { method: "POST" });
      await loadSuggestions();
    } catch (err) {
      handleApiError(err);
      suggestionsError = errorMessage(err, "Falha ao gerar sugestões.");
    } finally {
      generatingSuggestions = false;
    }
  }
```

E chamar `loadSuggestions()` dentro de `loadOverview()` (após carregar `failureRates`), ou no `onMount` junto das outras cargas.

- [ ] **Step 3: Render na seção de produção**

Em `frontend/src/routes/insights/+page.svelte`, logo após a tabela de taxa de falha (dentro da mesma `<section class="panel">` de produção ou numa nova), adicionar:

```svelte
    <div class="suggest-head">
      <h3 class="form-title">Sugestões da IA</h3>
      <button class="tiny" on:click={generateSuggestions} disabled={generatingSuggestions}>
        {generatingSuggestions ? "Gerando…" : (suggestions?.generated_at ? "Regerar" : "Gerar sugestões")}
      </button>
    </div>
    {#if suggestionsError}<div class="banner alert">{suggestionsError}</div>{/if}
    {#if suggestions && suggestions.stale && suggestions.generated_at}
      <p class="hint">Há novas falhas desde a última geração — clique em Regerar.</p>
    {/if}
    {#if suggestions && suggestions.suggestions.length > 0}
      <ul class="suggest-list">
        {#each suggestions.suggestions as s}
          <li><strong class="mono">{s.material_type}</strong> — {s.advice}</li>
        {/each}
      </ul>
    {:else if suggestions && !suggestions.generated_at}
      <p class="empty">Sem sugestões ainda. Gere a partir das falhas registradas.</p>
    {/if}
```

- [ ] **Step 4: Verificar**

Run: `cd frontend && npm run check`
Expected: nenhum erro NOVO (os 5 pré-existentes de `library`/`low_spool_threshold_g` podem permanecer).

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(ui): sugestões de IA na aba Insights (gerar sob demanda + cache)"
```

---

## Self-review (cobertura do spec §6)

- Pipeline de embeddings das falhas → Task 2 (`fill_failure_embeddings`). ✓
- Busca por similaridade (cosine) para compactar/deduplicar falhas → Task 3 (`gather_failures`). ✓
- Sugestões "o que vigiar" por material via LLM, sob demanda + cache → Tasks 3–4. ✓
- Exibição na aba Insights com gerar/regerar e flag de desatualizado → Task 5. ✓
- **Desvio consciente (custo):** parsing por evento (`llm_tags`) foi substituído por uma única chamada de geração que parseia+sugere ao mesmo tempo. A coluna `llm_tags` permanece para uso futuro; não é preenchida nesta fase. Alinhado com o spec ("IA lê o vetor e sugere") e com o objetivo de economizar tokens.
- **Tabela sempre-visível de taxa de falha (§6a):** já entregue na Fase A.
