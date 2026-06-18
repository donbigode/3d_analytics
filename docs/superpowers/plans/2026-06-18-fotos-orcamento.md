# Fotos no orçamento — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anexar fotos a um orçamento em dois níveis (capa do orçamento + por item), exibidas no app e no PDF do cliente, com galeria de várias fotos.

**Architecture:** Tabela única `quote_photos` (`quote_item_id` NULL = capa). Storage espelha `branding.py`, redimensiona com Pillow. API de upload/delete + endpoint `/raw` aberto (capability URL por UUID, igual ao logo). PDF (WeasyPrint) embute via `file://`. Frontend na página do orçamento.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic, Pillow, WeasyPrint, pytest via Docker, SvelteKit.

**Spec:** `docs/superpowers/specs/2026-06-18-fotos-orcamento-design.md`

**Comandos:** testes/lint/migração rodam via `docker compose run --rm api …`. Após mexer no `pyproject.toml`: `docker compose build api`.

---

## File Structure

- `backend/infra/db/models/quote_photo.py` — model `QuotePhoto` (+ export no `__init__`).
- `migrations/versions/0028_quote_photos.py` — tabela.
- `pyproject.toml` — `pillow`.
- `backend/infra/storage/quote_photos.py` — `save_photo`, `delete_photo`, `absolute_uri`.
- `backend/api/schemas/quotes.py` — `QuotePhotoOut`, `photos` em `QuoteItemOut`/`QuoteOut`.
- `backend/api/routes/quotes.py` — rotas de foto + wiring no `_quote_out` + cleanup no `delete_item` + fotos no `get_pdf`.
- `backend/infra/pdf/templates/quote.html` — grade de capa + miniatura por item.
- `frontend/src/lib/types.ts`, `frontend/src/routes/quotes/[id]/+page.svelte` — galeria.
- `backend/tests/api/conftest.py` — cleanup da tabela nova.

---

## Task 1: Migração + model `QuotePhoto`

**Files:**
- Create: `backend/infra/db/models/quote_photo.py`, `migrations/versions/0028_quote_photos.py`
- Modify: `backend/infra/db/models/__init__.py`, `backend/tests/api/conftest.py`

- [ ] **Step 1: Model**

`backend/infra/db/models/quote_photo.py`:

```python
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.db.base import Base


class QuotePhoto(Base):
    """Foto anexada a um orçamento (capa) ou a um item (quote_item_id != NULL)."""
    __tablename__ = "quote_photos"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    quote_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quote_item_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("quote_items.id", ondelete="CASCADE"), nullable=True, index=True
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False, default="image/jpeg")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: Export no `__init__`**

Em `backend/infra/db/models/__init__.py`, adicionar o import (junto dos outros `quote_*`):
```python
from backend.infra.db.models.quote_photo import QuotePhoto
```
e `"QuotePhoto"` no `__all__` (perto de `"QuoteItem", "QuoteService"`).

- [ ] **Step 3: Migração**

`migrations/versions/0028_quote_photos.py` (última revisão é `0027_export_config`):

```python
"""quote_photos (fotos no orçamento)

Revision ID: 0028_quote_photos
Revises: 0027_export_config
Create Date: 2026-06-18 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "0028_quote_photos"
down_revision: Union[str, Sequence[str], None] = "0027_export_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quote_photos",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("quote_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quote_item_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("quote_items.id", ondelete="CASCADE"), nullable=True),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(40), nullable=False, server_default="image/jpeg"),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("width", sa.Integer, nullable=False, server_default="0"),
        sa.Column("height", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_quote_photos_quote_id", "quote_photos", ["quote_id"])
    op.create_index("ix_quote_photos_quote_item_id", "quote_photos", ["quote_item_id"])


def downgrade() -> None:
    op.drop_table("quote_photos")
```

- [ ] **Step 4: Cleanup nos testes**

Em `backend/tests/api/conftest.py`: importar `QuotePhoto` (junto dos outros imports de model) e adicionar `QuotePhoto.__table__` como **o primeiro** item da tupla de limpeza (tem FK para quotes e quote_items, então apaga antes deles).

- [ ] **Step 5: Aplicar e verificar**

Run: `docker compose run --rm api alembic upgrade head`
Expected: aplica `0028_quote_photos` sem erro.

- [ ] **Step 6: Commit**

```bash
git add backend/infra/db/models/quote_photo.py backend/infra/db/models/__init__.py migrations/versions/0028_quote_photos.py backend/tests/api/conftest.py
git commit -m "feat(fotos): migração + model QuotePhoto"
```

---

## Task 2: Pillow + storage `save_photo`

**Files:**
- Modify: `pyproject.toml`
- Create: `backend/infra/storage/quote_photos.py`
- Test: `backend/tests/infra/test_quote_photos_storage.py`

- [ ] **Step 1: Dep + rebuild**

Em `pyproject.toml`, adicionar `"pillow>=10"` às dependências.
Run: `docker compose build api`
Run: `docker compose run --rm api python -c "import PIL; print(PIL.__version__)"`
Expected: imprime a versão.

- [ ] **Step 2: Teste**

`backend/tests/infra/test_quote_photos_storage.py`:

```python
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from backend.infra.storage import quote_photos


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def test_save_photo_resizes_and_reencodes_jpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(quote_photos, "get_settings",
                        lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    saved = quote_photos.save_photo(_png(4000, 3000), "foto.PNG")
    assert saved.content_type == "image/jpeg"
    assert max(saved.width, saved.height) == 1600          # reduziu pro lado maior
    assert saved.storage_path.startswith("quote_photos/")
    assert (tmp_path / saved.storage_path).exists()
    assert saved.size_bytes > 0


def test_save_photo_rejects_bad_type(tmp_path, monkeypatch):
    monkeypatch.setattr(quote_photos, "get_settings",
                        lambda: SimpleNamespace(storage_dir=str(tmp_path)))
    with pytest.raises(ValueError):
        quote_photos.save_photo(b"not an image", "evil.txt")
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/infra/test_quote_photos_storage.py -q`
Expected: FAIL — módulo inexistente.

- [ ] **Step 4: Implementar**

`backend/infra/storage/quote_photos.py`:

```python
import io
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from backend.settings import get_settings

MAX_DIM = 1600
ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}


@dataclass
class SavedPhoto:
    storage_path: str
    content_type: str
    size_bytes: int
    width: int
    height: int


def save_photo(content: bytes, filename: str) -> SavedPhoto:
    """Valida, corrige orientação EXIF, redimensiona pra MAX_DIM e reencoda JPEG."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        raise ValueError("tipo de arquivo não suportado")
    try:
        img = Image.open(io.BytesIO(content))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as exc:
        raise ValueError("imagem inválida") from exc
    img.thumbnail((MAX_DIM, MAX_DIM))  # só reduz, mantém proporção

    settings = get_settings()
    photos_dir = Path(settings.storage_dir) / "quote_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    dest = photos_dir / f"{uuid4().hex}.jpg"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    data = buf.getvalue()
    dest.write_bytes(data)
    return SavedPhoto(
        storage_path=str(dest.relative_to(settings.storage_dir)),
        content_type="image/jpeg",
        size_bytes=len(data),
        width=img.width,
        height=img.height,
    )


def delete_photo(storage_path: str | None) -> None:
    if not storage_path:
        return
    p = Path(get_settings().storage_dir) / storage_path
    if p.exists():
        p.unlink()


def absolute_uri(storage_path: str) -> str:
    return (Path(get_settings().storage_dir) / storage_path).as_uri()
```

- [ ] **Step 5: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/infra/test_quote_photos_storage.py -q`
Expected: PASS (2).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml backend/infra/storage/quote_photos.py backend/tests/infra/test_quote_photos_storage.py
git commit -m "feat(fotos): pillow + storage save_photo (resize/reencode)"
```

---

## Task 3: API upload/delete/raw + schema

**Files:**
- Modify: `backend/api/schemas/quotes.py`, `backend/api/routes/quotes.py`
- Test: `backend/tests/api/test_quote_photos.py`

- [ ] **Step 1: Schemas**

Em `backend/api/schemas/quotes.py`, adicionar a classe (antes de `QuoteItemOut`):

```python
class QuotePhotoOut(BaseModel):
    id: str
    quote_item_id: str | None
    url: str
    width: int
    height: int
    sort_order: int
```

E adicionar o campo `photos` em `QuoteItemOut` e em `QuoteOut` (ambos, no fim da classe):
```python
    photos: list[QuotePhotoOut] = []
```

- [ ] **Step 2: Teste**

`backend/tests/api/test_quote_photos.py`:

```python
import io

import pytest
import sqlalchemy as sa
from PIL import Image

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, QuoteItem, User


def _png(w: int = 1200, h: int = 900) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


async def _quote_with_item():
    async with session_module.SessionFactory() as s:
        user = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.PERSONAL.value, user_id=user.id,
                  status=QuoteStatus.DRAFT.value)
        s.add(q); await s.commit()
        item = QuoteItem(quote_id=q.id, name="peça", gcode_meta={}, quantity=1)
        s.add(item); await s.commit()
        return str(q.id), str(item.id)


@pytest.mark.asyncio
async def test_upload_cover_and_item_photo(auth_client):
    qid, item_id = await _quote_with_item()

    # capa (2000x1500 -> redimensiona pra 1600 no maior lado)
    r = await auth_client.post(f"/quotes/{qid}/photos",
                               files={"file": ("capa.png", _png(2000, 1500), "image/png")})
    assert r.status_code == 200, r.text
    cover = r.json()
    assert cover["quote_item_id"] is None
    assert cover["url"].endswith("/raw")
    assert max(cover["width"], cover["height"]) == 1600

    # foto de item
    r = await auth_client.post(f"/quotes/{qid}/photos",
                               files={"file": ("p.png", _png(800, 600), "image/png")},
                               data={"quote_item_id": item_id})
    assert r.status_code == 200, r.text
    assert r.json()["quote_item_id"] == item_id

    # aparece no QuoteOut (capa) e no item
    qq = (await auth_client.get(f"/quotes/{qid}")).json()
    assert len(qq["photos"]) == 1
    assert len(qq["items"][0]["photos"]) == 1

    # /raw serve a imagem
    raw = await auth_client.get(cover["url"])
    assert raw.status_code == 200
    assert raw.headers["content-type"] == "image/jpeg"

    # PDF gera com foto presente
    pdf = await auth_client.get(f"/quotes/{qid}/pdf")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    # delete remove e /raw vira 404
    d = await auth_client.delete(f"/quotes/{qid}/photos/{cover['id']}")
    assert d.status_code == 204
    assert (await auth_client.get(cover["url"])).status_code == 404


@pytest.mark.asyncio
async def test_item_from_another_quote_rejected(auth_client):
    qid, _ = await _quote_with_item()
    _other_qid, other_item_id = await _quote_with_item()
    r = await auth_client.post(f"/quotes/{qid}/photos",
                               files={"file": ("p.png", _png(), "image/png")},
                               data={"quote_item_id": other_item_id})
    assert r.status_code == 400, r.text
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `docker compose run --rm api pytest backend/tests/api/test_quote_photos.py -q`
Expected: FAIL — rotas 404 / `photos` ausente.

- [ ] **Step 4: Imports + helper + rotas**

Em `backend/api/routes/quotes.py`, garantir os imports no topo (adicionar o que faltar):
```python
from fastapi import File, Form, UploadFile
from fastapi.responses import FileResponse
from backend.api.schemas.quotes import QuotePhotoOut
from backend.infra.db.models import QuotePhoto
from backend.infra.storage import quote_photos as photo_storage
```
(`UUID`, `Path`, `select`, `Response`, `HTTPException`, `Depends`, `require_user`, `db_session`, `get_app_settings`, `Quote`, `QuoteItem`, `router` já estão no módulo.)

Helper `_photo_out` (perto de `_quote_out`):
```python
def _photo_out(p: QuotePhoto) -> QuotePhotoOut:
    return QuotePhotoOut(
        id=str(p.id),
        quote_item_id=str(p.quote_item_id) if p.quote_item_id else None,
        url=f"/quotes/photos/{p.id}/raw",
        width=p.width, height=p.height, sort_order=p.sort_order,
    )
```

Rotas (adicionar no fim do arquivo, antes/depois das outras rotas de `router`):
```python
@router.post("/{quote_id}/photos", response_model=QuotePhotoOut)
async def add_photo(
    quote_id: UUID,
    file: UploadFile = File(...),
    quote_item_id: str | None = Form(None),
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    q = await session.get(Quote, quote_id)
    if not q:
        raise HTTPException(404)
    item_uuid = None
    if quote_item_id:
        item_uuid = UUID(quote_item_id)
        it = await session.get(QuoteItem, item_uuid)
        if it is None or it.quote_id != q.id:
            raise HTTPException(400, "item não pertence ao orçamento")
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(413, "imagem maior que 15MB")
    try:
        saved = photo_storage.save_photo(content, file.filename or "foto.jpg")
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    cond = QuotePhoto.quote_item_id.is_(None) if item_uuid is None else (QuotePhoto.quote_item_id == item_uuid)
    siblings = (await session.execute(
        select(QuotePhoto).where(QuotePhoto.quote_id == q.id, cond)
    )).scalars().all()
    photo = QuotePhoto(
        quote_id=q.id, quote_item_id=item_uuid,
        storage_path=saved.storage_path, content_type=saved.content_type,
        size_bytes=saved.size_bytes, width=saved.width, height=saved.height,
        sort_order=len(siblings),
    )
    session.add(photo)
    await session.commit()
    await session.refresh(photo)
    return _photo_out(photo)


@router.get("/photos/{photo_id}/raw")
async def serve_photo(photo_id: UUID, session: AsyncSession = Depends(db_session)):
    p = await session.get(QuotePhoto, photo_id)
    if not p:
        raise HTTPException(404)
    full = Path(get_app_settings().storage_dir) / p.storage_path
    if not full.exists():
        raise HTTPException(404)
    return FileResponse(full, media_type=p.content_type)


@router.delete("/{quote_id}/photos/{photo_id}", status_code=204)
async def delete_photo(
    quote_id: UUID, photo_id: UUID,
    _: User = Depends(require_user),
    session: AsyncSession = Depends(db_session),
):
    p = await session.get(QuotePhoto, photo_id)
    if p is None or p.quote_id != quote_id:
        raise HTTPException(404)
    photo_storage.delete_photo(p.storage_path)
    await session.delete(p)
    await session.commit()
    return Response(status_code=204)
```

NOTA de ordenação de rotas: declarar `serve_photo` (`/photos/{photo_id}/raw`) **antes** de qualquer rota `GET /{quote_id}` não é necessário (têm contagens de segmento diferentes), mas se houver conflito de match, mover `serve_photo` pra cima resolve.

- [ ] **Step 5: Wiring no `_quote_out`**

Em `_quote_out` (em `backend/api/routes/quotes.py`), depois de carregar `items`/`services` e antes de montar `items_out`, carregar as fotos e separar capa × item:
```python
    photos = (await session.execute(
        select(QuotePhoto)
        .where(QuotePhoto.quote_id == q.id)
        .order_by(QuotePhoto.sort_order, QuotePhoto.created_at)
    )).scalars().all()
    cover_photos = [_photo_out(p) for p in photos if p.quote_item_id is None]
    photos_by_item: dict[str, list[QuotePhotoOut]] = {}
    for p in photos:
        if p.quote_item_id is not None:
            photos_by_item.setdefault(str(p.quote_item_id), []).append(_photo_out(p))
```
No `QuoteItemOut(...)` dentro do list-comprehension, adicionar:
```python
            photos=photos_by_item.get(str(it.id), []),
```
No `QuoteOut(...)` final, adicionar:
```python
        photos=cover_photos,
```

- [ ] **Step 6: Cleanup de arquivos no `delete_item`**

Em `delete_item` (rota `DELETE /{quote_id}/items/{item_id}`), antes de deletar o item, remover os arquivos das fotos do item (o cascade do banco apaga as linhas, mas não os arquivos):
```python
    item_photos = (await session.execute(
        select(QuotePhoto).where(QuotePhoto.quote_item_id == item_id)
    )).scalars().all()
    for p in item_photos:
        photo_storage.delete_photo(p.storage_path)
```

- [ ] **Step 7: Rodar e ver passar**

Run: `docker compose run --rm api pytest backend/tests/api/test_quote_photos.py -q`
Expected: PASS (2).

- [ ] **Step 8: Commit**

```bash
git add backend/api/schemas/quotes.py backend/api/routes/quotes.py backend/tests/api/test_quote_photos.py
git commit -m "feat(fotos): API upload/delete/raw + photos no QuoteOut"
```

---

## Task 4: Fotos no PDF

**Files:**
- Modify: `backend/api/routes/quotes.py` (builder do `data` no `get_pdf`), `backend/infra/pdf/templates/quote.html`

- [ ] **Step 1: Builder do PDF**

No `get_pdf` (em `backend/api/routes/quotes.py`), depois de carregar `items`, carregar as fotos e montar os URIs `file://`:
```python
    all_photos = (await session.execute(
        select(QuotePhoto)
        .where(QuotePhoto.quote_id == q.id)
        .order_by(QuotePhoto.sort_order, QuotePhoto.created_at)
    )).scalars().all()
    cover_photo_uris = [
        photo_storage.absolute_uri(p.storage_path)
        for p in all_photos if p.quote_item_id is None
    ]
    item_photo_uris: dict[str, list[str]] = {}
    for p in all_photos:
        if p.quote_item_id is not None:
            item_photo_uris.setdefault(str(p.quote_item_id), []).append(
                photo_storage.absolute_uri(p.storage_path)
            )
```
Dentro do `item_dicts.append({...})`, adicionar a chave:
```python
                "photos": item_photo_uris.get(str(it.id), []),
```
No dict `data = {...}`, adicionar:
```python
        "cover_photos": cover_photo_uris,
```

- [ ] **Step 2: Template**

Em `backend/infra/pdf/templates/quote.html`, logo após a linha `<p>Status: {{ quote.status }}</p>`, adicionar a grade de capa:
```html
{% if cover_photos %}
<div style="display:flex; flex-wrap:wrap; gap:6px; margin:10px 0;">
  {% for url in cover_photos %}
    <img src="{{ url }}" style="width:160px; height:160px; object-fit:cover; border:1px solid #e5e7eb; border-radius:4px;">
  {% endfor %}
</div>
{% endif %}
```
E na célula do nome da peça (dentro do `{% for it in items %}`, dentro do primeiro `<td>`, depois do bloco de `model_source_url`), adicionar as miniaturas do item:
```html
        {% if it.photos %}
          <div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:4px;">
            {% for url in it.photos %}
              <img src="{{ url }}" style="width:64px; height:64px; object-fit:cover; border:1px solid #e5e7eb; border-radius:3px;">
            {% endfor %}
          </div>
        {% endif %}
```

- [ ] **Step 3: Verificar (coberto pelo teste da Task 3)**

Run: `docker compose run --rm api pytest backend/tests/api/test_quote_photos.py -q`
Expected: PASS — o teste já faz `GET /quotes/{id}/pdf` com foto de capa presente e checa `%PDF`. Se falhar por `KeyError` no template, conferir que `cover_photos` e `it.photos` estão no `data`.

- [ ] **Step 4: Commit**

```bash
git add backend/api/routes/quotes.py backend/infra/pdf/templates/quote.html
git commit -m "feat(fotos): embute capa e fotos de item no PDF"
```

---

## Task 5: Frontend — galeria na página do orçamento

**Files:**
- Modify: `frontend/src/lib/types.ts`, `frontend/src/routes/quotes/[id]/+page.svelte`

- [ ] **Step 1: Tipos**

Em `frontend/src/lib/types.ts`, adicionar:
```typescript
export type QuotePhoto = {
  id: string;
  quote_item_id: string | null;
  url: string;
  width: number;
  height: number;
  sort_order: number;
};
```
E adicionar `photos: QuotePhoto[]` no tipo `QuoteItem` (linha ~105 de `types.ts`) e no tipo `Quote` (linha ~135). O tipo `Quote` já tem `items: QuoteItem[]`.

- [ ] **Step 2: Upload/delete + galeria de capa**

Em `frontend/src/routes/quotes/[id]/+page.svelte`, adicionar funções (seguindo o padrão do logo em `settings/+page.svelte`):
```typescript
  let photoVersion = 0; // cache-bust

  async function uploadPhoto(file: File, quoteItemId: string | null) {
    const fd = new FormData();
    fd.append("file", file);
    if (quoteItemId) fd.append("quote_item_id", quoteItemId);
    const res = await fetch(`/api/quotes/${id}/photos`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(await res.text());
    photoVersion += 1;
    await load(); // `load()` é a função existente da página que faz GET /quotes/{id}
  }

  async function deletePhoto(photoId: string) {
    await api(`/quotes/${id}/photos/${photoId}`, { method: "DELETE" });
    photoVersion += 1;
    await reload();
  }
```
NOTA: `load()` (linha ~202 da página) já faz `quote = await api<Quote>(/quotes/${id})`; `id` é o param da rota já disponível. `api` já está importado.

Seção de capa no markup (perto do topo do orçamento):
```svelte
<section class="photos">
  <h3>Fotos</h3>
  <div class="photo-grid">
    {#each quote.photos as p (p.id)}
      <figure class="photo">
        <img src={`/api${p.url}?v=${photoVersion}`} alt="" />
        <button class="ghost danger" on:click={() => deletePhoto(p.id)}>×</button>
      </figure>
    {/each}
    <label class="photo-add">
      + foto
      <input type="file" accept="image/*" capture
             on:change={(e) => {
               const f = (e.currentTarget as HTMLInputElement).files?.[0];
               if (f) uploadPhoto(f, null);
             }} hidden />
    </label>
  </div>
</section>
```

- [ ] **Step 3: Foto por item**

Na linha/card de cada item, adicionar um bloco análogo, passando o id do item:
```svelte
<div class="photo-grid small">
  {#each it.photos as p (p.id)}
    <figure class="photo">
      <img src={`/api${p.url}?v=${photoVersion}`} alt="" />
      <button class="ghost danger" on:click={() => deletePhoto(p.id)}>×</button>
    </figure>
  {/each}
  <label class="photo-add">
    + foto
    <input type="file" accept="image/*" capture
           on:change={(e) => {
             const f = (e.currentTarget as HTMLInputElement).files?.[0];
             if (f) uploadPhoto(f, it.id);
           }} hidden />
  </label>
</div>
```
Estilo (no `<style>` da página), miniaturas quadradas com botão excluir sobreposto:
```css
  .photo-grid { display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .photo-grid.small { gap: 0.3rem; }
  .photo { position: relative; margin: 0; }
  .photo img { width: 110px; height: 110px; object-fit: cover; border: 1px solid var(--line); border-radius: 4px; }
  .photo-grid.small .photo img { width: 64px; height: 64px; }
  .photo button { position: absolute; top: 2px; right: 2px; padding: 0 0.35rem; line-height: 1.4; }
  .photo-add { display: inline-flex; align-items: center; justify-content: center;
    width: 110px; height: 110px; border: 1px dashed var(--line-strong);
    border-radius: 4px; cursor: pointer; color: var(--muted); font-size: 0.85rem; }
```

- [ ] **Step 4: Check**

Run: `cd frontend && npm run check`
Expected: sem erros novos (só os pré-existentes de library/spools).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/routes/quotes/[id]/+page.svelte
git commit -m "feat(fotos): galeria de fotos (capa + por item) na página do orçamento"
```

---

## Task 6: Verificação

- [ ] **Step 1:** `docker compose run --rm api pytest backend/tests -q` → tudo PASS.
- [ ] **Step 2:** `cd frontend && npm run check` → sem erros novos.
- [ ] **Step 3:** `docker compose run --rm api ruff check backend/infra/storage/quote_photos.py backend/api/routes/quotes.py backend/infra/db/models/quote_photo.py` → sem erros novos (E702 pré-existente tolerado).

---

## Notas

- **`/raw` é aberto** (sem auth), acessível só com o UUID da foto (capability URL) — mesmo nível do `GET /settings/logo` atual.
- **Sem dedup**: cada upload vira um arquivo `quote_photos/<uuid>.jpg`.
- **Sem reordenação** no v1: `sort_order` = ordem de inserção.
- **Não existe** endpoint de deletar orçamento inteiro; cleanup de arquivo é feito no `delete_item` e no `DELETE` de foto. Fotos órfãs no disco (caso raro) podem ser limpas depois.
- **Reload no frontend** = `load()` (já existe na página, faz `GET /quotes/{id}`).
- **EXIF**: `save_photo` chama `ImageOps.exif_transpose` (corrige foto girada); coberto pela implementação, sem teste dedicado no v1.
