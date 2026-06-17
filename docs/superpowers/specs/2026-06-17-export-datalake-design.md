# Export de entidades para Data Lake (S3 / Databricks)

**Data:** 2026-06-17
**Status:** aprovado no brainstorming, pronto para plano de implementação.

## 1. Objetivo

Exportar **todas as entidades** do banco como **Parquet bruto (bronze)** para um destino
configurável — **S3** ou **volume do Databricks** — para alimentar um ELT medallion num
**outro repositório** (reconstrução do analítico, Delta tables com time-travel). Este lado
só **aterrissa o dado bruto**; nada de transformação.

A integração é **configurável na aba Integrações** (`/config`): seletor de destino, tokens
e caminhos, toggle de envio diário, e botão de export sob demanda.

## 2. Config — `export_config` (tabela singleton)

Tabela `export_config` (id=1), segredos **mascarados** na leitura (padrão `_mask` do
`/config`):

| Campo | Tipo | Papel |
|---|---|---|
| `id` | int PK (=1) | singleton |
| `enabled` | bool default false | liga/pausa o **envio diário** (o force ignora) |
| `destination` | `String(20)` (`s3`\|`databricks`) | destino ativo |
| `s3_bucket` / `s3_region` / `s3_prefix` | `String` | config S3 |
| `s3_access_key_id` / `s3_secret_access_key` | `String` (segredo) | credenciais S3 |
| `databricks_host` | `String` | ex.: `https://dbc-xxxx.cloud.databricks.com` |
| `databricks_token` | `String` (segredo) | PAT do Free Edition |
| `databricks_volume_path` | `String` | ex.: `/Volumes/<catalog>/<schema>/<volume>/3d_analytics` |
| `last_run_at` | timestamptz null | último export |
| `last_run_status` | `String(20)` null | `ok` \| `error` |
| `last_run_detail` | `Text` null | resumo (entidades/linhas) ou mensagem de erro |

Migração: cria a tabela. Os segredos seguem em texto na tabela (mesmo nível dos tokens
meli/reddit já existentes em `Settings`).

## 3. Motor de export

### 3.1 Registry de entidades (`core/export/entities.py`)
Exporta **todas as tabelas** mapeadas, **exceto** as de segredo (`settings`,
`export_config`). `users` é exportada **sem** `password_hash`. Cada entrada:
`(nome, model, colunas_excluídas)`. Lista derivada de `backend.infra.db.models` (quotes,
quote_items, quote_services, sales, expenses, material_versions, material_consumptions,
spools, clients, services, production_events, assets, data_source_runs, keyword_ideas,
keyword_observations, llm_digests, llm_suggestions, production_suggestions,
calibration_insights, watcher_inbox_files, users[sem hash]).

### 3.2 Serialização (`core/export/serialize.py`)
`table_to_parquet(rows: list[dict]) -> bytes` via **`pyarrow`**. Coerção por valor:
- `datetime` → timestamp; `bool`/`int`/`float` nativos; `str` nativo;
- `UUID` → `str`; **`Decimal` → `str`** (sem perda); `dict`/`list` (JSONB) → string JSON;
- `None` preservado.
Tabela vazia → Parquet só com schema das colunas (sem linhas).

### 3.3 Runner (`core/export/runner.py`)
`run_export(session, config, destination) -> dict`:
1. `run_ts = datetime.now(UTC)` formatado `YYYYMMDDTHHMMSSZ`.
2. Para cada entidade: lê todas as linhas (SELECT *), serializa, e
   `destination.put(f"{run_ts}/{nome}.parquet", data)`.
3. Atualiza `last_run_at/status/detail` na `export_config` e retorna
   `{run_ts, entidades, linhas_por_entidade, ok|erro}`.
Carrega cada tabela inteira em memória (escala atual ok).

## 4. Destinos (`core/export/destinations.py`)

Interface `Destination.put(rel_path: str, data: bytes) -> None`. Factory
`build_destination(config)` escolhe pelo `config.destination`.

- **`S3Destination`** (`boto3`, nova dep): cliente com `aws_access_key_id`/`secret`/`region`;
  `put_object(Bucket=s3_bucket, Key=f"{s3_prefix.rstrip('/')}/{rel_path}", Body=data)`.
- **`DatabricksDestination`** (`httpx`, já existe): `PUT
  {host}/api/2.0/fs/files{volume_path.rstrip('/')}/{rel_path}?overwrite=true`,
  header `Authorization: Bearer {token}`, body = bytes (Files API de Volumes do Unity
  Catalog). Levanta erro em status >= 400.

## 5. Disparo

- **Force:** `POST /config/export/run` → roda `run_export` **agora** (ignora `enabled`),
  retorna o resumo. Erro de destino vira `last_run_status='error'` + detalhe e o endpoint
  retorna `200` com `{ok: false, detail}` (ver §7 nota), não 5xx.
- **Diário:** `backend/infra/scheduler/export.py` com `export_once()` (lê config; se
  `enabled`, roda) + `run_forever()` (dorme 24h, repete, captura erros) +
  `start_background_task()`. Registrado no lifespan do `app.py`, como os schedulers de
  trends/llm.
- **Pause:** `enabled=false` faz o diário pular; o force sempre roda.

## 6. API + UI

- **API (estende `/config`):**
  - `GET /config/export` → config com segredos mascarados + `last_run_*`.
  - `PUT /config/export` → atualiza campos (não sobrescreve segredo quando vier mascarado/vazio).
  - `POST /config/export/run` → force export, retorna resumo.
- **UI (aba Integrações `/config`):** seção "Data Lake / Export":
  - seletor de destino (S3 | Databricks) mostrando os campos do destino escolhido;
  - toggle **Ativar envio diário** (`enabled`);
  - botão **Exportar agora** + spinner;
  - status do último run (`last_run_at`, `last_run_status`, `last_run_detail`).

## 7. Testes e deps

- **Deps novas:** `pyarrow`, `boto3` (no `pyproject`).
- **Testes (mockados, sem rede):**
  - `serialize`: rows com UUID/Decimal/datetime/JSON → parquet → ler de volta com pyarrow,
    conferir colunas e valores (Decimal vira str).
  - `runner` com `FakeDestination` (captura `put`): um arquivo por entidade sob `<run_ts>/`,
    `last_run_status='ok'`, contagem de linhas correta.
  - `S3Destination`: cliente boto3 mockado → `put_object` com Bucket/Key corretos.
  - `DatabricksDestination`: httpx mockado → `PUT` na URL/headers corretos; status 4xx levanta.
  - `/config/export` GET/PUT mascarando segredos; `POST /config/export/run` retorna resumo.
  - gate do diário: `export_once` não chama o runner quando `enabled=false`.
- **Migração Alembic:** tabela `export_config`.
- **Frontend:** `npm run check`.

**Nota (erro no force):** o force retorna `200` com `{ok: false, detail}` quando o destino
falha (credencial inválida etc.), gravando `last_run_status='error'`; assim a UI mostra o
erro sem tratar como 500.

## 8. Fora de escopo (YAGNI)

- ELT / medallion / Delta tables (outro repositório).
- Export incremental/CDC (sempre snapshot full por run).
- Envio simultâneo para os dois destinos (um destino ativo por vez).
- Particionamento por data dentro de cada entidade (a pasta `run_ts` já versiona).
- Agendamento configurável de horário (diário fixo de 24h).
