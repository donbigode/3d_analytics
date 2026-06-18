# Fotos no orçamento — Design

**Data:** 2026-06-18
**Branch:** `feat/fotos-orcamento`

## Objetivo

Permitir anexar fotos a um orçamento em **dois níveis** — uma galeria de **capa** (orçamento inteiro) e uma galeria **por item/peça** — exibidas na tela do orçamento e no **PDF** enviado ao cliente. Várias fotos por galeria (ordem de upload no v1).

## Decisões

- **Dois níveis** numa única tabela (`quote_item_id` NULL = capa).
- **App + PDF.**
- **Galeria** (múltiplas fotos). `sort_order` persistido; arrastar-pra-ordenar fica pra depois (v1 = ordem de upload).
- **Pillow** entra como dependência pra redimensionar (foto de celular é grande demais pro PDF).
- Servir imagem pro `<img>` via endpoint **aberto, protegido por UUID** (capability URL), mesmo padrão do `GET /settings/logo` atual.

## Modelo de dados

Tabela nova `quote_photos` (migração `0028_quote_photos`):

| coluna | tipo | nota |
|---|---|---|
| `id` | UUID PK | |
| `quote_id` | UUID FK→quotes `ON DELETE CASCADE`, NOT NULL, index | |
| `quote_item_id` | UUID FK→quote_items `ON DELETE CASCADE`, NULL | **NULL = capa do orçamento** |
| `storage_path` | String(500) | relativo ao `storage_dir` |
| `content_type` | String(40) | `image/jpeg` após reencode |
| `size_bytes` | Integer | pós-resize |
| `width` / `height` | Integer | pós-resize |
| `sort_order` | Integer, default 0 | ordenação da galeria |
| `created_at` | DateTime(tz) | |

## Storage — `backend/infra/storage/quote_photos.py`

Espelha `branding.py`.

- `save_photo(content: bytes, filename: str) -> SavedPhoto` — valida extensão/tipo (`jpg/jpeg/png/webp`), abre com Pillow, corrige orientação EXIF, redimensiona pra caber em **1600×1600** (mantém proporção, só reduz), reencoda **JPEG q85**, grava em `storage/quote_photos/<uuid>.jpg`. Retorna path relativo + content_type + size + width + height.
- `delete_photo(path: str | None)` — remove o arquivo se existir.
- Limite de upload: rejeita request > **15 MB** (antes do resize) via validação no route.

`SavedPhoto` é um dataclass simples (path, content_type, size_bytes, width, height).

## API — `backend/api/routes/quotes.py` (+ schema)

- `POST /quotes/{quote_id}/photos` — multipart `file` (+ form opcional `quote_item_id`). Sem item → capa. Com item → valida que o item pertence ao orçamento. Cria a linha (`sort_order` = max+1 da galeria correspondente). Retorna `QuotePhotoOut`.
- `DELETE /quotes/{quote_id}/photos/{photo_id}` — remove linha + arquivo.
- `GET /quotes/photos/{photo_id}/raw` — **sem `require_user`**, serve `FileResponse`. Acesso por UUID (capability URL).
- `QuotePhotoOut`: `id`, `quote_item_id`, `url` (`/quotes/photos/<id>/raw`), `width`, `height`, `sort_order`.
- `QuoteOut` ganha `photos: list[QuotePhotoOut]` (só capa, `quote_item_id is None`).
- `QuoteItemOut` ganha `photos: list[QuotePhotoOut]` (as do item).
- Na montagem do `QuoteOut`, carregar todas as `quote_photos` do orçamento e separar capa × item, ordenando por `sort_order, created_at`.

Reordenação (`PUT .../photos/order`) **fora do escopo do v1** — `sort_order` fica só com a ordem de inserção.

## PDF — `backend/infra/pdf/templates/quote.html` + `render.py`

- `render.py` passa, junto do contexto, os **caminhos absolutos** (`file://…`) das fotos (capa + por item), resolvidos a partir do `storage_dir`.
- Template: grade de capa no topo (depois do cabeçalho) e miniatura ao lado de cada item quando houver foto. CSS de impressão (tamanho fixo, `object-fit: cover`).

## Frontend — `frontend/src/routes/quotes/[id]/+page.svelte` + `types.ts`

- Tipo `QuotePhoto` e campos `photos` em `Quote` e no item.
- Seção **"Fotos"** (capa): `<input type="file" accept="image/*" capture>` (abre câmera no celular), grade de miniaturas com botão excluir. Upload via `FormData` em `fetch("/api/quotes/{id}/photos")` (mesmo jeito do logo).
- Por item: botão "+ foto" pequeno na linha/card do item, com miniaturas + excluir (envia `quote_item_id` no FormData).
- Cache-bust com `?v=` após upload/delete (igual ao logo).

## Limpeza

- `DELETE` de foto remove o arquivo.
- Cascade no banco apaga as linhas ao deletar orçamento/item; os **arquivos** são limpos best-effort no handler de delete do orçamento/item (carrega os paths antes do delete e remove do disco).

## Testes

- **storage**: resize reduz dimensão e reencoda JPEG; rejeita tipo inválido; corrige EXIF (imagem girada).
- **API**: upload capa e upload item aparecem em `QuoteOut.photos` / `QuoteItemOut.photos`; `quote_item_id` de outro orçamento → 400; delete remove linha+arquivo; `/raw` serve bytes; item de outro orçamento rejeitado.
- **PDF**: template inclui `<img>` quando há fotos (smoke no `render`).
- **frontend**: `npm run check` sem erros novos.

## Fora de escopo (v1)

- Arrastar-pra-ordenar a galeria.
- Legenda/caption por foto.
- Deduplicação por hash (cada upload é um arquivo).
