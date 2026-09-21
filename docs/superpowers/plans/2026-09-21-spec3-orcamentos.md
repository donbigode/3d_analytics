# Spec 3 — Orçamentos: clonar e ver o filamento usado — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replicar um orçamento existente com um clique, e mostrar na tela qual bobina foi realmente consumida em cada peça.

**Architecture:** `POST /quotes/{id}/clone` copia registros e **também os arquivos em disco** (gcode e fotos), remapeando os vínculos; `QuoteItemOut` ganha a lista de consumos que já existe em `material_consumptions` e nunca subia para a API.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest, SvelteKit 2 + Svelte 5, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-21-orcamento-clone-filamento-design.md`

## Global Constraints

- **Depende das Specs 0 e 1** — pacote `backend/api/routes/quotes/`, `$lib/format`, `quoteNumber`, `QuoteOut.seq`.
- **Nenhuma migração.** Os dois pedidos são atendidos com o schema atual.
- O clone nasce sempre `draft`, de qualquer status de origem.
- Consumo de filamento **não vai para o PDF** — é custo interno, e `retail_mode` existe para escondê-lo do cliente.
- Tudo roda via Docker Compose: `make test`, `make lint`, `make e2e`.
- Mensagens de commit terminam com `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Armadilhas de armazenamento conferidas no código

Duas, que a implementação precisa respeitar:

1. **Gcode** — `backend/infra/storage/gcodes.py` grava em
   `<STORAGE_DIR>/gcodes/<quote_id>/<filename>`. Copiar só o registro faria o item
   do clone apontar para a pasta do orçamento **original**; o reparse do clone
   quebraria assim que o original fosse limpo.
2. **Fotos** — `backend/infra/storage/quote_photos.py` grava em
   `quote_photos/<uuid>.jpg`, diretório **plano**, e `delete_photo()` dá `unlink`
   no arquivo. Compartilhar `storage_path` entre original e clone faria apagar a
   foto do original **apagar a imagem do clone**.

---

### Task 1: `POST /quotes/{id}/clone` — registros

Primeiro só os registros do banco, sem arquivos. As Tasks 2 e 3 acrescentam gcode e fotos.

**Files:**
- Modify: `backend/api/routes/quotes/crud.py`
- Test: `backend/tests/api/test_quote_clone.py`

**Interfaces:**
- Consumes: `Quote`, `QuoteItem`, `QuoteService`, `QuotePerson`, `_quote_out`.
- Produces: `POST /quotes/{quote_id}/clone` → `201` com `QuoteOut`.

- [ ] **Step 1: Escrever o teste que falha**

Create `backend/tests/api/test_quote_clone.py`:

```python
"""Clone de orçamento.

O clone é um orçamento novo que ainda não aconteceu: nasce em rascunho,
sem timestamps de ciclo, sem consumo de material, sem evento de produção
e sem linha no contábil.
"""
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialConsumption, ProductionEvent, Quote, QuoteItem, Sale, User,
)


async def _quote_com_item(kind=QuoteKind.COMMERCIAL, status=QuoteStatus.ENTREGUE) -> Quote:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=kind.value, user_id=u.id, status=status.value,
                  markup_pct=Decimal("80"), min_charge=Decimal("25"),
                  notes="orçamento original", retail_mode=True)
        s.add(q)
        await s.flush()
        s.add(QuoteItem(quote_id=q.id, name="porta-caneta", filename=None,
                        gcode_meta={"filament_m": 12.5, "time_s": 3600, "material": "PLA"},
                        quantity=2, is_multi_color=True,
                        model_source_url="https://printables.com/model/1",
                        model_source_author="alguém", model_source_license="CC-BY"))
        await s.commit()
        await s.refresh(q)
        return q


@pytest.mark.asyncio
async def test_clone_nasce_em_rascunho_sem_timestamps(auth_client):
    orig = await _quote_com_item()
    r = await auth_client.post(f"/quotes/{orig.id}/clone")
    assert r.status_code == 201, r.text
    novo = r.json()
    assert novo["id"] != str(orig.id)
    assert novo["status"] == "draft"
    for campo in ("finalized_at", "approved_at", "produced_at", "delivered_at"):
        assert novo[campo] is None, f"{campo} deveria estar limpo no clone"


@pytest.mark.asyncio
async def test_clone_tem_seq_proprio(auth_client):
    orig = await _quote_com_item()
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    assert novo["seq"] != orig.seq
    assert novo["seq"] > orig.seq


@pytest.mark.asyncio
async def test_clone_copia_config_comercial(auth_client):
    orig = await _quote_com_item()
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    assert Decimal(novo["markup_pct"]) == orig.markup_pct
    assert Decimal(novo["min_charge"]) == orig.min_charge
    assert novo["retail_mode"] == orig.retail_mode
    assert novo["kind"] == orig.kind


@pytest.mark.asyncio
async def test_clone_copia_itens_com_todos_os_campos(auth_client):
    orig = await _quote_com_item()
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    assert len(novo["items"]) == 1
    it = novo["items"][0]
    assert it["name"] == "porta-caneta"
    assert it["quantity"] == 2
    assert it["is_multi_color"] is True
    assert it["gcode_meta"]["filament_m"] == 12.5
    assert it["model_source_url"] == "https://printables.com/model/1"
    assert it["model_source_author"] == "alguém"
    assert it["model_source_license"] == "CC-BY"


@pytest.mark.asyncio
async def test_clone_anota_a_origem_nas_notas(auth_client):
    orig = await _quote_com_item()
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    assert novo["notes"].startswith(f"Clone de #{orig.seq:04d}")
    assert "orçamento original" in novo["notes"]


@pytest.mark.asyncio
async def test_clone_nao_copia_historico_de_producao(auth_client):
    orig = await _quote_com_item()
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    async with session_module.SessionFactory() as s:
        item_ids = (await s.execute(
            sa.select(QuoteItem.id).where(QuoteItem.quote_id == novo["id"]))).scalars().all()
        cons = (await s.execute(sa.select(sa.func.count()).select_from(MaterialConsumption)
                                .where(MaterialConsumption.quote_item_id.in_(item_ids)))).scalar()
        assert cons == 0
        eventos = (await s.execute(sa.select(sa.func.count()).select_from(ProductionEvent)
                                   .where(ProductionEvent.quote_id == novo["id"]))).scalar()
        assert eventos == 0
        vendas = (await s.execute(sa.select(sa.func.count()).select_from(Sale)
                                  .where(Sale.quote_id == novo["id"]))).scalar()
        assert vendas == 0


@pytest.mark.asyncio
async def test_clone_de_pessoal_preserva_tipo(auth_client):
    orig = await _quote_com_item(kind=QuoteKind.PERSONAL, status=QuoteStatus.PRODUZIDO)
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    assert novo["kind"] == "personal"
    assert novo["status"] == "draft"


@pytest.mark.asyncio
async def test_clone_de_orcamento_inexistente_da_404(auth_client):
    import uuid
    r = await auth_client.post(f"/quotes/{uuid.uuid4()}/clone")
    assert r.status_code == 404
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_clone.py -v
```

Expected: FAIL — 404/405 em todos, a rota não existe.

- [ ] **Step 3: Implementar o clone dos registros**

Em `backend/api/routes/quotes/crud.py`:

```python
@router.post("/{quote_id}/clone", response_model=QuoteOut, status_code=201)
async def clone_quote(
    quote_id: UUID,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    """Replica um orçamento como rascunho novo.

    O clone é um orçamento que ainda não aconteceu: status draft, sem
    timestamps de ciclo, sem consumo de material, sem evento de produção
    e sem linha no contábil. Copia configuração comercial, peças,
    serviços, fotos e pessoas — mais os ARQUIVOS em disco, porque
    compartilhá-los faria o original apagar o que é do clone.
    """
    orig = await session.get(Quote, quote_id)
    if not orig:
        raise HTTPException(404)

    novo = Quote(
        kind=orig.kind,
        client_id=orig.client_id,
        user_id=user.id,
        status=QuoteStatus.DRAFT,
        markup_pct=orig.markup_pct,
        min_charge=orig.min_charge,
        retail_mode=orig.retail_mode,
        notes=_notas_do_clone(orig),
    )
    session.add(novo)
    await session.flush()   # precisa do id para as pastas de arquivo

    itens_orig = (
        await session.execute(select(QuoteItem).where(QuoteItem.quote_id == orig.id))
    ).scalars().all()
    mapa_itens: dict[UUID, UUID] = {}
    for it in itens_orig:
        copia = QuoteItem(
            quote_id=novo.id,
            name=it.name,
            filename=it.filename,          # o arquivo em si é copiado na Task 2
            gcode_meta=dict(it.gcode_meta or {}),
            material_version_id=it.material_version_id,
            quantity=it.quantity,
            depreciation_rate_override=it.depreciation_rate_override,
            failure_rate_override=it.failure_rate_override,
            is_multi_color=it.is_multi_color,
            model_source_url=it.model_source_url,
            model_source_author=it.model_source_author,
            model_source_license=it.model_source_license,
            asset_id=it.asset_id,
        )
        session.add(copia)
        await session.flush()
        mapa_itens[it.id] = copia.id

    servicos = (
        await session.execute(select(QuoteService).where(QuoteService.quote_id == orig.id))
    ).scalars().all()
    for qs in servicos:
        session.add(QuoteService(quote_id=novo.id, service_id=qs.service_id,
                                 quantity=qs.quantity, rate=qs.rate))

    pessoas = (
        await session.execute(select(QuotePerson).where(QuotePerson.quote_id == orig.id))
    ).scalars().all()
    for qp in pessoas:
        session.add(QuotePerson(quote_id=novo.id, person_id=qp.person_id))

    await session.commit()
    return await _quote_out(session, novo)


def _notas_do_clone(orig: Quote) -> str:
    """Rastreabilidade sem coluna nova: a origem vai na primeira linha
    das notas (decisão registrada na Spec 3 §3.5)."""
    cabecalho = f"Clone de #{orig.seq:04d}"
    return f"{cabecalho}\n{orig.notes}" if orig.notes else cabecalho
```

Importar `QuoteService`, `QuotePerson` e `select` conforme o que já está no módulo.

- [ ] **Step 4: Rodar e confirmar que passa**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_clone.py -v
make test 2>&1 | tail -5
make lint
```

Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/quotes/crud.py backend/tests/api/test_quote_clone.py
git commit -m "feat(orçamentos): POST /quotes/{id}/clone — registros

Clone nasce em rascunho, sem timestamps, consumo, evento ou venda.
Origem anotada nas notas (Clone de #0042), sem coluna nova.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Clone do arquivo de gcode

**Files:**
- Modify: `backend/infra/storage/gcodes.py`
- Modify: `backend/api/routes/quotes/crud.py`
- Test: `backend/tests/api/test_quote_clone.py` (estende)

**Interfaces:**
- Consumes: `save_gcode` já existente.
- Produces: `def copy_gcode(src_rel: str, dest_quote_id: UUID) -> str | None` em `gcodes.py` — devolve o caminho relativo novo, ou `None` se a origem não existir em disco.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar a `backend/tests/api/test_quote_clone.py`:

```python
from pathlib import Path

from backend.settings import get_settings


@pytest.mark.asyncio
async def test_clone_copia_o_arquivo_de_gcode_para_a_pasta_nova(auth_client):
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    conteudo = b"; generated by PrusaSlicer\nG1 X0 Y0\n; filament used [mm] = 12500\n"
    r = await auth_client.post(
        f"/quotes/{qid}/items",
        files={"file": ("peca.gcode", conteudo, "text/plain")},
        data={"name": "peça", "quantity": "1"},
    )
    assert r.status_code == 201, r.text

    novo = (await auth_client.post(f"/quotes/{qid}/clone")).json()
    async with session_module.SessionFactory() as s:
        item = (await s.execute(
            sa.select(QuoteItem).where(QuoteItem.quote_id == novo["id"]))).scalars().one()
    assert item.filename is not None
    base = Path(get_settings().storage_dir)
    assert (base / item.filename).exists(), "arquivo do clone não existe em disco"
    assert novo["id"] in item.filename, "clone aponta para a pasta do original"


@pytest.mark.asyncio
async def test_clone_sem_arquivo_em_disco_nao_falha(auth_client):
    """Histórico anterior ao armazenamento: o registro tem filename mas o
    arquivo sumiu. O clone segue, com o item sem arquivo."""
    orig = await _quote_com_item()
    async with session_module.SessionFactory() as s:
        it = (await s.execute(
            sa.select(QuoteItem).where(QuoteItem.quote_id == orig.id))).scalars().one()
        it.filename = "gcodes/inexistente/sumiu.gcode"
        await s.commit()

    r = await auth_client.post(f"/quotes/{orig.id}/clone")
    assert r.status_code == 201, r.text
    async with session_module.SessionFactory() as s:
        copia = (await s.execute(
            sa.select(QuoteItem).where(QuoteItem.quote_id == r.json()["id"]))).scalars().one()
    assert copia.filename is None
```

Conferir a assinatura real do endpoint de adicionar item antes de rodar — o
`data=`/`files=` acima precisa bater com o que `items.py` espera:

```bash
grep -n "async def add_item" -A 20 backend/api/routes/quotes/items.py
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_clone.py -v -k gcode
```

Expected: FAIL — o clone aponta para a pasta do original.

- [ ] **Step 3: Implementar `copy_gcode`**

Em `backend/infra/storage/gcodes.py`:

```python
import shutil
from uuid import UUID


def copy_gcode(src_rel: str | None, dest_quote_id: UUID) -> str | None:
    """Copia um gcode já armazenado para a pasta de outro orçamento.

    Usado pelo clone: compartilhar o caminho faria o item do clone apontar
    para a pasta do original, e o reparse quebraria assim que o original
    fosse limpo.

    Devolve o caminho relativo novo, ou None quando a origem não existe em
    disco (histórico anterior ao armazenamento) — nesse caso o clone segue
    com o item sem arquivo.
    """
    if not src_rel:
        return None
    storage_dir = Path(get_settings().storage_dir)
    src = storage_dir / src_rel
    if not src.is_file():
        return None
    base = storage_dir / "gcodes" / str(dest_quote_id)
    base.mkdir(parents=True, exist_ok=True)
    dest = base / src.name
    shutil.copy2(src, dest)
    return str(dest.relative_to(storage_dir))
```

- [ ] **Step 4: Usar no clone**

Em `clone_quote`, dentro do laço de itens, trocar `filename=it.filename` por:

```python
            filename=copy_gcode(it.filename, novo.id),
```

Importando `copy_gcode` de `backend.infra.storage.gcodes`.

- [ ] **Step 5: Rodar e confirmar que passa**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_clone.py -v
make test 2>&1 | tail -5
make lint
```

- [ ] **Step 6: Commit**

```bash
git add backend/infra/storage/gcodes.py backend/api/routes/quotes/crud.py \
        backend/tests/api/test_quote_clone.py
git commit -m "feat(orçamentos): clone copia o gcode para a pasta do novo orçamento

Compartilhar o caminho quebraria o reparse do clone. Origem ausente em
disco não aborta — o item vem sem arquivo.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Clone das fotos

**Files:**
- Modify: `backend/infra/storage/quote_photos.py`
- Modify: `backend/api/routes/quotes/crud.py`
- Test: `backend/tests/api/test_quote_clone.py` (estende)

**Interfaces:**
- Consumes: `save_photo`, `delete_photo` já existentes.
- Produces: `def copy_photo_file(src_rel: str) -> SavedPhoto | None` em `quote_photos.py`.

- [ ] **Step 1: Escrever o teste que falha**

Acrescentar a `backend/tests/api/test_quote_clone.py`:

```python
import io

from PIL import Image

from backend.infra.db.models import QuotePhoto


def _jpeg(cor=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), cor).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_clone_copia_fotos_com_arquivo_proprio(auth_client):
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    r = await auth_client.post(f"/quotes/{qid}/photos",
                               files={"file": ("foto.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text

    novo = (await auth_client.post(f"/quotes/{qid}/clone")).json()
    assert len(novo["photos"]) == 1

    async with session_module.SessionFactory() as s:
        orig_foto = (await s.execute(sa.select(QuotePhoto)
                                     .where(QuotePhoto.quote_id == qid))).scalars().one()
        nova_foto = (await s.execute(sa.select(QuotePhoto)
                                     .where(QuotePhoto.quote_id == novo["id"]))).scalars().one()
    assert nova_foto.storage_path != orig_foto.storage_path, "clone compartilhou o arquivo"
    base = Path(get_settings().storage_dir)
    assert (base / nova_foto.storage_path).exists()


@pytest.mark.asyncio
async def test_apagar_foto_do_original_nao_afeta_o_clone(auth_client):
    """Regressão da armadilha: quote_photos é diretório plano e delete_photo
    dá unlink no arquivo."""
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    foto_id = (await auth_client.post(
        f"/quotes/{qid}/photos",
        files={"file": ("foto.jpg", _jpeg(), "image/jpeg")})).json()["id"]

    novo = (await auth_client.post(f"/quotes/{qid}/clone")).json()
    r = await auth_client.delete(f"/quotes/{qid}/photos/{foto_id}")
    assert r.status_code == 204

    async with session_module.SessionFactory() as s:
        nova_foto = (await s.execute(sa.select(QuotePhoto)
                                     .where(QuotePhoto.quote_id == novo["id"]))).scalars().one()
    base = Path(get_settings().storage_dir)
    assert (base / nova_foto.storage_path).exists(), "apagar do original matou a foto do clone"


@pytest.mark.asyncio
async def test_foto_de_item_aponta_para_o_item_do_clone(auth_client):
    orig = await _quote_com_item()
    async with session_module.SessionFactory() as s:
        item = (await s.execute(
            sa.select(QuoteItem).where(QuoteItem.quote_id == orig.id))).scalars().one()
        item_id = item.id
    r = await auth_client.post(f"/quotes/{orig.id}/photos",
                               files={"file": ("foto.jpg", _jpeg(), "image/jpeg")},
                               data={"quote_item_id": str(item_id)})
    assert r.status_code == 200, r.text

    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    async with session_module.SessionFactory() as s:
        ids_do_clone = set((await s.execute(
            sa.select(QuoteItem.id).where(QuoteItem.quote_id == novo["id"]))).scalars().all())
        nova_foto = (await s.execute(sa.select(QuotePhoto)
                                     .where(QuotePhoto.quote_id == novo["id"]))).scalars().one()
    assert nova_foto.quote_item_id in ids_do_clone
    assert nova_foto.quote_item_id != item_id
```

Conferir antes a assinatura real de `POST /quotes/{id}/photos` (nome do campo de
arquivo e como `quote_item_id` é recebido):

```bash
grep -n "async def upload_photo\|quote_item_id" -A 15 backend/api/routes/quotes/photos.py | head -40
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_clone.py -v -k foto
```

- [ ] **Step 3: Implementar `copy_photo_file`**

Em `backend/infra/storage/quote_photos.py`:

```python
def copy_photo_file(src_rel: str | None) -> SavedPhoto | None:
    """Copia uma foto já armazenada para um arquivo novo.

    Usado pelo clone. Compartilhar o storage_path faria delete_photo() no
    original apagar a imagem do clone — quote_photos é diretório plano,
    sem pasta por orçamento.
    """
    if not src_rel:
        return None
    settings = get_settings()
    src = Path(settings.storage_dir) / src_rel
    if not src.is_file():
        return None
    # Reusa save_photo para manter o mesmo reencode e os mesmos metadados.
    return save_photo(src.read_bytes(), src.name)
```

- [ ] **Step 4: Usar no clone**

Em `clone_quote`, depois do laço de itens (que já montou `mapa_itens`):

```python
    fotos = (
        await session.execute(select(QuotePhoto).where(QuotePhoto.quote_id == orig.id))
    ).scalars().all()
    for foto in fotos:
        copia_arquivo = copy_photo_file(foto.storage_path)
        if copia_arquivo is None:
            continue   # arquivo sumiu do disco: não replica um registro quebrado
        session.add(QuotePhoto(
            quote_id=novo.id,
            quote_item_id=mapa_itens.get(foto.quote_item_id) if foto.quote_item_id else None,
            storage_path=copia_arquivo.storage_path,
            content_type=copia_arquivo.content_type,
            size_bytes=copia_arquivo.size_bytes,
            width=copia_arquivo.width,
            height=copia_arquivo.height,
            sort_order=foto.sort_order,
        ))
```

- [ ] **Step 5: Limpar arquivos se o commit falhar**

Envolver a parte de arquivos para que um erro no commit não deixe registro
apontando para arquivo inexistente. Arquivo órfão é o modo de falha aceito
(Spec 3 §3.6):

```python
    escritos: list[str] = []   # caminhos relativos gravados por copy_gcode/copy_photo_file
    try:
        # ... laços de itens e fotos, acumulando em `escritos` cada caminho
        #     devolvido por copy_gcode() e copy_photo_file()
        await session.commit()
    except Exception:
        await session.rollback()
        _remover_arquivos(escritos)
        raise
```

Com o auxiliar, em `crud.py` — genérico de propósito, porque limpa tanto gcode
quanto foto, e `delete_photo()` do módulo de fotos seria o nome errado para isso:

```python
def _remover_arquivos(caminhos_relativos: list[str]) -> None:
    """Limpeza de melhor esforço quando o commit do clone falha.

    Arquivo órfão é o modo de falha aceito (Spec 3 §3.6); registro
    apontando para arquivo inexistente, não.
    """
    base = Path(get_settings().storage_dir)
    for rel in caminhos_relativos:
        alvo = base / rel
        if alvo.is_file():
            alvo.unlink(missing_ok=True)
```

- [ ] **Step 6: Rodar e confirmar que passa**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_clone.py -v
make test 2>&1 | tail -5
make lint
```

- [ ] **Step 7: Commit**

```bash
git add backend/infra/storage/quote_photos.py backend/api/routes/quotes/crud.py \
        backend/tests/api/test_quote_clone.py
git commit -m "feat(orçamentos): clone copia fotos com arquivo próprio

quote_photos é diretório plano e delete_photo dá unlink — compartilhar o
storage_path faria apagar do original matar a foto do clone. Teste de
regressão explícito. quote_item_id remapeado para o item do clone.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Botão de clonar na interface

**Files:**
- Modify: `frontend/src/routes/quotes/+page.svelte`
- Modify: `frontend/src/routes/quotes/[id]/+page.svelte`

**Interfaces:**
- Consumes: `POST /quotes/{id}/clone`, `action` de `$lib/resource`.
- Produces: nada.

- [ ] **Step 1: Ligar na lista**

Em `quotes/+page.svelte`:

```ts
  import { goto } from "$app/navigation";
  import { action } from "$lib/resource";

  const clonar = action(
    (id: string) => api<Quote>(`/quotes/${id}/clone`, { method: "POST" }),
    { errorMessage: "Falha ao clonar o orçamento." },
  );

  async function clonarEAbrir(id: string) {
    const novo = await clonar.run(id);
    if (novo) await goto(`/quotes/${novo.id}`);
  }
```

Na célula de ações, ao lado de "abrir":

```svelte
              <button class="tiny ghost" disabled={$clonar.pending}
                      on:click={() => clonarEAbrir(q.id)}>
                {$clonar.pending ? "clonando…" : "clonar"}
              </button>
```

Copiar arquivos leva tempo perceptível com muitas fotos — o `pending` é o que
evita a pessoa clicar duas vezes e criar dois clones.

- [ ] **Step 2: Ligar no detalhe**

No painel Ações de `quotes/[id]/+page.svelte`, o mesmo botão, disponível em
qualquer status (o clone sempre nasce rascunho).

- [ ] **Step 3: Verificar**

```bash
cd frontend && npm run check && npm run build
```

Clonar um orçamento entregue com foto e gcode; conferir que abre o rascunho novo
com as peças, que o número é outro, e que a nota começa com "Clone de #".

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/quotes/
git commit -m "feat(ui): botão clonar na lista e no detalhe do orçamento

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `consumptions` na API

**Files:**
- Modify: `backend/api/schemas/quotes.py`
- Modify: `backend/api/routes/quotes/_shared.py` (`_quote_out`)
- Test: `backend/tests/api/test_quote_consumptions.py`

**Interfaces:**
- Consumes: `MaterialConsumption`, `Spool`.
- Produces: `ConsumptionOut` e `QuoteItemOut.consumptions: list[ConsumptionOut]`.

- [ ] **Step 1: Escrever o teste que falha**

Create `backend/tests/api/test_quote_consumptions.py`:

```python
"""O filamento realmente consumido sobe para a API.

O dado já existia em material_consumptions — bobina, gramas, custo
congelado e data — e nunca chegava à tela: depois do rascunho, a coluna
Material mostrava só o polímero do gcode ("PLA").
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialConsumption, Quote, QuoteItem, Spool, User,
)


async def _quote_com_consumo(n_consumos: int = 1):
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        sp = Spool(material_type="PLA", color="Preto", manufacturer="Voolt3D",
                   purchased_at=datetime.now(timezone.utc), purchased_price=Decimal("100.00"),
                   initial_grams=Decimal("1000"), remaining_grams=Decimal("900"))
        s.add(sp)
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("100"),
                  min_charge=Decimal("0"))
        s.add(q)
        await s.flush()
        it = QuoteItem(quote_id=q.id, name="porta-caneta",
                       gcode_meta={"filament_m": 12.5, "material": "PLA"}, quantity=1)
        s.add(it)
        await s.flush()
        base = datetime(2026, 9, 12, tzinfo=timezone.utc)
        for i in range(n_consumos):
            s.add(MaterialConsumption(
                quote_item_id=it.id, spool_id=sp.id, grams_used=Decimal("48.20"),
                unit_cost_snapshot=Decimal("0.1000"),
                consumed_at=base + timedelta(days=2 * i),
            ))
        await s.commit()
        return q, it, sp


@pytest.mark.asyncio
async def test_rascunho_vem_sem_consumos(auth_client):
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    await auth_client.post(f"/quotes/{qid}/items", data={"name": "peça", "quantity": "1"})
    item = (await auth_client.get(f"/quotes/{qid}")).json()["items"][0]
    assert item["consumptions"] == []


@pytest.mark.asyncio
async def test_consumo_traz_bobina_gramas_e_custo(auth_client):
    q, it, sp = await _quote_com_consumo()
    item = (await auth_client.get(f"/quotes/{q.id}")).json()["items"][0]
    assert len(item["consumptions"]) == 1
    c = item["consumptions"][0]
    assert c["spool_id"] == str(sp.id)
    assert c["material_type"] == "PLA"
    assert c["color"] == "Preto"
    assert c["manufacturer"] == "Voolt3D"
    assert Decimal(c["grams_used"]) == Decimal("48.20")
    assert Decimal(c["unit_cost_snapshot"]) == Decimal("0.1000")
    assert Decimal(c["custo_total"]) == Decimal("4.82")
    assert "PLA" in c["spool_label"] and "Preto" in c["spool_label"]


@pytest.mark.asyncio
async def test_reimpressao_gera_duas_linhas_ordenadas(auth_client):
    """Falhou → reproduziu consome material duas vezes. Hoje a tela não
    registra nenhuma das duas."""
    q, _it, _sp = await _quote_com_consumo(n_consumos=2)
    item = (await auth_client.get(f"/quotes/{q.id}")).json()["items"][0]
    assert len(item["consumptions"]) == 2
    datas = [c["consumed_at"] for c in item["consumptions"]]
    assert datas == sorted(datas), "consumos devem vir em ordem cronológica"


@pytest.mark.asyncio
async def test_custo_congelado_nao_muda_quando_a_bobina_encarece(auth_client):
    q, _it, sp = await _quote_com_consumo()
    async with session_module.SessionFactory() as s:
        bobina = await s.get(Spool, sp.id)
        bobina.purchased_price = Decimal("300.00")
        await s.commit()
    item = (await auth_client.get(f"/quotes/{q.id}")).json()["items"][0]
    assert Decimal(item["consumptions"][0]["unit_cost_snapshot"]) == Decimal("0.1000")


@pytest.mark.asyncio
async def test_consumos_nao_reintroduzem_n_mais_1(auth_client):
    from sqlalchemy import event

    q, it, sp = await _quote_com_consumo()
    async with session_module.SessionFactory() as s:
        for i in range(6):
            extra = QuoteItem(quote_id=q.id, name=f"peça {i}",
                              gcode_meta={"filament_m": 5.0}, quantity=1)
            s.add(extra)
            await s.flush()
            s.add(MaterialConsumption(quote_item_id=extra.id, spool_id=sp.id,
                                      grams_used=Decimal("10"),
                                      unit_cost_snapshot=Decimal("0.1")))
        await s.commit()

    contador = {"n": 0}

    def antes(conn, cursor, statement, params, context, executemany):
        contador["n"] += 1

    event.listen(session_module.engine.sync_engine, "before_cursor_execute", antes)
    try:
        r = await auth_client.get(f"/quotes/{q.id}")
        assert r.status_code == 200
    finally:
        event.remove(session_module.engine.sync_engine, "before_cursor_execute", antes)

    assert contador["n"] < 20, (
        f"{contador['n']} queries para 7 itens — consumos estão sendo buscados por item"
    )
```

- [ ] **Step 2: Rodar e confirmar que falha**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_consumptions.py -v
```

Expected: FAIL — `KeyError: 'consumptions'`.

- [ ] **Step 3: Adicionar o schema**

Em `backend/api/schemas/quotes.py`, antes de `QuoteItemOut`:

```python
class ConsumptionOut(BaseModel):
    """Uma baixa de material: qual bobina, quantas gramas, a que custo e quando.

    Um ciclo de produção por linha — reimpressão depois de falha aparece
    como entrada adicional, com data própria.
    """
    spool_id: str
    spool_label: str
    material_type: str
    color: str | None
    manufacturer: str | None
    grams_used: Decimal
    unit_cost_snapshot: Decimal
    custo_total: Decimal
    consumed_at: datetime
```

E no `QuoteItemOut`:

```python
    consumptions: list[ConsumptionOut] = []
```

- [ ] **Step 4: Carregar em `_quote_out`, em lote**

Em `backend/api/routes/quotes/_shared.py`, antes de montar os `QuoteItemOut`:

```python
async def _consumptions_map(
    session: AsyncSession, item_ids: list[UUID]
) -> dict[UUID, list[ConsumptionOut]]:
    """Consumos de todos os itens do orçamento numa query só — buscar por
    item reintroduziria o N+1 que a Spec 2 acabou de tirar do contábil."""
    if not item_ids:
        return {}
    rows = (
        await session.execute(
            select(MaterialConsumption, Spool)
            .join(Spool, Spool.id == MaterialConsumption.spool_id)
            .where(MaterialConsumption.quote_item_id.in_(item_ids))
            .order_by(MaterialConsumption.consumed_at)
        )
    ).all()
    out: dict[UUID, list[ConsumptionOut]] = {}
    for cons, sp in rows:
        out.setdefault(cons.quote_item_id, []).append(
            ConsumptionOut(
                spool_id=str(sp.id),
                spool_label=_spool_label(sp),
                material_type=sp.material_type,
                color=sp.color,
                manufacturer=sp.manufacturer,
                grams_used=cons.grams_used,
                unit_cost_snapshot=cons.unit_cost_snapshot,
                custo_total=(cons.grams_used * cons.unit_cost_snapshot).quantize(Decimal("0.01")),
                consumed_at=cons.consumed_at,
            )
        )
    return out


def _spool_label(sp: Spool) -> str:
    """Mesmo formato usado na tela de produzir, para a pessoa reconhecer a
    bobina nos dois lugares."""
    partes = [sp.material_type]
    if sp.color:
        partes.append(sp.color)
    if sp.manufacturer:
        partes.append(sp.manufacturer)
    partes.append(str(sp.id)[:8])
    return " · ".join(partes)
```

Conferir o formato real usado na tela de produzir antes de fixar `_spool_label`:

```bash
grep -rn "spool" frontend/src/routes/quotes/\[id\]/+page.svelte | grep -i "label\|option" | head
```

E usar `consumptions=mapa.get(it.id, [])` ao montar cada `QuoteItemOut`.

- [ ] **Step 5: Rodar e confirmar que passa**

```bash
docker compose run --rm api pytest backend/tests/api/test_quote_consumptions.py -v
make test 2>&1 | tail -5
make lint
```

- [ ] **Step 6: Atualizar os tipos do frontend**

Em `frontend/src/lib/types.ts`:

```ts
export type Consumption = {
  spool_id: string;
  spool_label: string;
  material_type: string;
  color: string | null;
  manufacturer: string | null;
  grams_used: string;
  unit_cost_snapshot: string;
  custo_total: string;
  consumed_at: string;
};
```

E `consumptions: Consumption[]` em `QuoteItem`.

- [ ] **Step 7: Commit**

```bash
git add backend/api/schemas/quotes.py backend/api/routes/quotes/_shared.py \
        backend/tests/api/test_quote_consumptions.py frontend/src/lib/types.ts
git commit -m "feat(api): QuoteItemOut.consumptions — filamento realmente usado

O dado já estava em material_consumptions e nunca subia. Carregado em
lote; teste de contagem de queries impede o N+1.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Filamento na tela do orçamento

**Files:**
- Modify: `frontend/src/routes/quotes/[id]/+page.svelte`

**Interfaces:**
- Consumes: `QuoteItem.consumptions` (Task 5), `money`/`num`/`date` de `$lib/format`.
- Produces: nada.

- [ ] **Step 1: Corrigir a coluna Material**

No ramo `{:else}` da célula de material (fora de rascunho), trocar
`{it.gcode_meta?.material ?? "—"}` por:

```svelte
                      {#if (it.consumptions ?? []).length > 0}
                        {@const ultimo = it.consumptions[it.consumptions.length - 1]}
                        <span title={ultimo.spool_label}>
                          {ultimo.material_type}{ultimo.color ? ` · ${ultimo.color}` : ""}
                        </span>
                        {#if it.consumptions.length > 1}
                          <span class="badge" title="Houve mais de um ciclo de produção"
                            >{it.consumptions.length} baixas</span>
                        {/if}
                      {:else}
                        {it.gcode_meta?.material ?? "—"}
                        <span class="badge estimativa" title="Nenhuma baixa registrada ainda — este é o material do gcode, não a bobina usada.">estimativa</span>
                      {/if}
                      {it.is_multi_color ? " · multicolor" : ""}
```

- [ ] **Step 2: Painel "Filamento consumido"**

Logo abaixo da seção Peças, visível só quando há consumo:

```svelte
{#if totalBaixas > 0}
  <section class="panel">
    <div class="panel-head">
      <h2 class="section-title">
        Filamento consumido <span class="count">· {totalBaixas} {totalBaixas === 1 ? "baixa" : "baixas"}</span>
      </h2>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Peça</th><th>Bobina</th>
            <th class="right">Gramas</th><th class="right">Custo</th><th>Data</th>
          </tr>
        </thead>
        <tbody>
          {#each linhasConsumo as l}
            <tr>
              <td>{l.peca}</td>
              <td class="mono" title={l.c.spool_label}>
                {l.c.material_type}{l.c.color ? ` · ${l.c.color}` : ""}{l.c.manufacturer ? ` · ${l.c.manufacturer}` : ""}
              </td>
              <td class="right mono">{fmtNum(l.c.grams_used, 1)} g</td>
              <td class="right mono">{fmtMoney(l.c.custo_total)}</td>
              <td class="mono dim">{fmtDate(l.c.consumed_at)}</td>
            </tr>
          {/each}
        </tbody>
        <tfoot>
          <tr>
            <td colspan="2" class="mono">total</td>
            <td class="right mono">{fmtNum(totalGramas, 1)} g</td>
            <td class="right mono">{fmtMoney(totalCusto)}</td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
  </section>
{/if}
```

Com os derivados no `<script>`:

```ts
  // Achata item × consumo numa lista só, ordenada por data — é assim que a
  // reimpressão depois de falha fica visível como linha própria.
  $: linhasConsumo = (quote?.items ?? [])
    .flatMap((it) => (it.consumptions ?? []).map((c) => ({ peca: it.name, c })))
    .sort((a, b) => a.c.consumed_at.localeCompare(b.c.consumed_at));
  $: totalBaixas = linhasConsumo.length;
  $: totalGramas = linhasConsumo.reduce((s, l) => s + Number(l.c.grams_used), 0);
  $: totalCusto = linhasConsumo.reduce((s, l) => s + Number(l.c.custo_total), 0);
```

- [ ] **Step 3: Verificar**

```bash
cd frontend && npm run check && npm run build
```

Abrir um orçamento produzido: a coluna Material mostra a bobina, o painel lista
as baixas com total. Abrir um orçamento apenas orçado: a coluna mostra o material
do gcode com o selo "estimativa" e o painel não aparece. Forçar uma falha e
reproduzir: duas linhas com datas diferentes.

- [ ] **Step 4: Confirmar que o PDF não mudou**

```bash
docker compose run --rm api pytest backend/tests/api/test_quotes_pdf.py -v
```

Expected: verde. O consumo é custo interno e não entra no PDF (Spec 3 §4.4).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/quotes/
git commit -m "feat(ui): painel de filamento consumido + coluna Material real

Fora de rascunho a coluna passa a mostrar a bobina, não só o polímero do
gcode. Reimpressão após falha aparece como linha própria, com data.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: E2E

**Files:**
- Create: `tests/e2e/clone-e-filamento.spec.ts`

- [ ] **Step 1: Escrever o teste**

Dois fluxos, reusando os helpers de login e criação de orçamento que já existem
em `tests/e2e/` — ler o spec existente antes de escrever:

1. Clonar da lista abre um rascunho com as mesmas peças e número diferente.
2. Um orçamento produzido exibe o painel "Filamento consumido" com a bobina.

- [ ] **Step 2: Rodar**

```bash
make up && make seed && make e2e
```

- [ ] **Step 3: Commit**

```bash
git add tests/e2e/clone-e-filamento.spec.ts
git commit -m "test(e2e): clone de orçamento e painel de filamento

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Critério de pronto da Spec 3

- [ ] `make test`, `make lint`, `make e2e` verdes.
- [ ] Clonar um orçamento entregue produz rascunho utilizável sem nenhum reupload.
- [ ] Apagar foto do original não afeta o clone (teste de regressão passa).
- [ ] Orçamento fora de rascunho mostra a bobina real, não só o polímero.
- [ ] Reimpressão após falha aparece como linha própria no painel.
- [ ] Nenhuma migração criada.
- [ ] PDF inalterado.
