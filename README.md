# 3D Print Orçamento & Analítico

Serviço web para precificar e acompanhar trabalhos de impressão 3D. Lê metadados de arquivos `.gcode` (Creality Print), aplica regras de custo + margem, gera orçamentos em PDF, controla inventário de filamento com consumo real e expõe um dashboard financeiro.

Operação inicial: rede local da oficina/casa. Arquitetura modular pronta pra migrar pra microsserviço AWS depois.

---

## Sumário

1. [Visão geral](#visão-geral)
2. [Stack](#stack)
3. [Como subir](#como-subir)
4. [Estrutura do repositório](#estrutura-do-repositório)
5. [Modelo de dados](#modelo-de-dados)
6. [Domínio e fluxos](#domínio-e-fluxos)
7. [API](#api)
8. [Frontend — página por página](#frontend--página-por-página)
9. [Nuances importantes](#nuances-importantes)
10. [Testes](#testes)
11. [Deploy / LAN](#deploy--lan)
12. [Backlog](#backlog-pós-mvp)

---

## Visão geral

O serviço resolve três coisas:

1. **Custo de produção real e detalhado** por impressão. Combina filamento, energia, depreciação da máquina, mão de obra e taxa de falha em uma fórmula auditável.
2. **Preço de venda (orçamento)** aplicando markup e um piso mínimo configurável. Gera PDF formal com a identidade visual da marca.
3. **Acompanhamento** do ciclo de vida (orçado → aprovado → produzido → entregue), com inventário de filamento e analítico financeiro do que entrou de receita vs o custo real.

Dois modos por orçamento: **comercial** (gera preço de venda; conta como receita) e **pessoal** (só despesa, workflow encurtado, sem mão de obra).

Spec autoritativo: [`docs/superpowers/specs/2026-06-06-3d-print-orcamento-design.md`](docs/superpowers/specs/2026-06-06-3d-print-orcamento-design.md).
Plano de implementação: [`docs/superpowers/plans/2026-06-06-3d-print-mvp.md`](docs/superpowers/plans/2026-06-06-3d-print-mvp.md).

---

## Stack

| Camada | Tecnologia | Por quê |
|---|---|---|
| Linguagem backend | Python 3.12 | Continuidade do script CLI original; ecossistema científico |
| Framework HTTP | FastAPI | Async nativo, OpenAPI grátis, validação por Pydantic |
| ORM | SQLAlchemy 2.x async + asyncpg | Pronto pra alta concorrência sem dor |
| Migrations | Alembic | Histórico auditável; obrigatório com Postgres |
| Banco | PostgreSQL 16 | SCD2 + JSONB + tipos numéricos exatos |
| Auth | argon2id (hash) + JWT em cookie HttpOnly | Senha forte; sem dor de refresh tokens no MVP |
| PDF | WeasyPrint (HTML → PDF) | Mesmo CSS que a tela; templates Jinja2 |
| Watcher | `watchfiles` (asyncio) | Sem polling pesado; reativo |
| Frontend | SvelteKit + adapter-static + Vite + vite-plugin-pwa | Leve, builds pequenos, PWA fácil |
| Containers | Docker + Docker Compose | Postgres + API com migrações no startup |
| Testes | pytest + httpx + Playwright | Unit, integração via ASGI, E2E |

---

## Como subir

### Pré-requisitos
- Docker Desktop (ou daemon equivalente)
- Node 18+ (para o frontend em dev)
- Make

### 1. Backend (API + DB)

```bash
cp .env.example .env          # ajuste pelo menos SESSION_SECRET
make up                       # sobe postgres + api (build na 1ª vez, ~3min)
```

A API roda na porta **8000**. O entrypoint do container faz `alembic upgrade head` antes de subir o Uvicorn, então toda migração nova aplica sozinha.

### 2. Primeiro usuário

```bash
make create-user              # interativo (nome + email + senha)
# ou:
make seed                     # cria t@t.com / pw idempotente (DEV apenas)
```

### 3. Frontend (dev com hot reload)

```bash
make fe-install               # npm install (1ª vez)
make fe-dev                   # Vite em http://localhost:5173
```

O Vite faz proxy de `/api/*` para `http://localhost:8000`, então cookies funcionam (mesma origem).

### 4. Acesso

| URL | Para que |
|---|---|
| `http://localhost:5173` | App em dev (com hot reload) |
| `http://localhost:8000/docs` | OpenAPI/Swagger (gerado pelo FastAPI) |
| `http://localhost:8000/healthz` | Liveness check |

### Makefile — comandos disponíveis

| Comando | O que faz |
|---|---|
| `make up` | Sobe `db` + `api` (build + migrations) |
| `make up-db` | Sobe só o Postgres (útil para Alembic local) |
| `make down` | Derruba os containers (volumes persistem) |
| `make logs` | Stream de logs do `api` |
| `make test` | Roda a suíte pytest **num DB separado** (`app_test`); dev fica intacto |
| `make lint` | `ruff check backend` |
| `make migrate` | `alembic upgrade head` manualmente |
| `make shell` | `bash` dentro do container `api` |
| `make create-user` | Cria usuário interativamente |
| `make seed` | Cria `t@t.com / pw` idempotente |
| `make fe-install` / `fe-dev` / `fe-build` | Node toolchain |
| `make e2e-install` / `make e2e` | Playwright |

---

## Estrutura do repositório

```
3d_analytics/
├── backend/                          # Python
│   ├── core/                         # Domínio puro: zero framework, zero DB
│   │   ├── gcode/                    # Parser dos arquivos .gcode
│   │   │   ├── parser.py             # parse_gcode_metadata() → GcodeMeta
│   │   │   └── dialects.py           # enum p/ slicers diferentes (Creality, Prusa, Bambu...)
│   │   ├── pricing/                  # Cálculo de custo e preço
│   │   │   ├── cost.py               # grams_from_meters, filament_cost, energy_cost, depreciation_cost
│   │   │   ├── labor.py              # LaborLine + labor_cost
│   │   │   ├── failure.py            # apply_failure(base, pct)
│   │   │   └── quote.py              # ItemInput, ServiceLine, compute_item_cost, compute_quote_total
│   │   ├── quote_service.py          # orquestração gcode → ItemInput (cola gcode + Material)
│   │   ├── security.py               # argon2id + JWT HS256 (hash_password / verify_password / make_jwt)
│   │   └── models.py                 # Enums compartilhados (QuoteKind, QuoteStatus, ServiceKind, ...)
│   │
│   ├── infra/                        # Adapters: I/O, DB, storage, PDF, watcher
│   │   ├── db/
│   │   │   ├── base.py               # DeclarativeBase
│   │   │   ├── session.py            # async engine + SessionFactory + get_session()
│   │   │   ├── models/               # 1 arquivo por entidade (User, Client, Quote, ...)
│   │   │   └── repos/                # Helpers de query (material SCD2, quote)
│   │   ├── storage/
│   │   │   ├── gcodes.py             # save_gcode(): persiste .gcode em <STORAGE_DIR>/gcodes/<quote_id>/
│   │   │   └── branding.py           # save_logo / delete_logo em <STORAGE_DIR>/branding/
│   │   ├── pdf/
│   │   │   ├── render.py             # render_quote_pdf(data) → bytes
│   │   │   └── templates/            # Jinja2: _base.html + quote.html
│   │   └── watcher/
│   │       └── runner.py             # asyncio task; observa WATCH_DIR; cria WatcherInboxFile
│   │
│   ├── api/                          # FastAPI: só transporte HTTP
│   │   ├── deps.py                   # db_session, require_user (autenticação por cookie)
│   │   ├── schemas/                  # Pydantic in/out (1 por recurso)
│   │   └── routes/                   # 1 router por recurso (auth, users, clients, materials, ...)
│   │
│   ├── tests/
│   │   ├── conftest.py               # Root: cria app_test, derruba+migra, fixtures globais
│   │   ├── core/                     # Unit do domínio puro
│   │   ├── infra/                    # PDF + watcher
│   │   └── api/                      # End-to-end via ASGI (httpx)
│   │
│   ├── app.py                        # entrypoint FastAPI; registra todos os routers + startup hook do watcher
│   ├── settings.py                   # pydantic-settings; lê do .env
│   └── cli.py                        # python -m backend.cli create-user / seed-dev / version
│
├── frontend/                         # SvelteKit
│   └── src/
│       ├── app.html / app.css        # shell HTML + estilos globais
│       ├── lib/
│       │   ├── api.ts                # fetch() wrapper com credentials: include
│       │   ├── branding.ts           # helpers p/ cor + logo
│       │   ├── guard.ts              # requireAuth(): redireciona se não logado
│       │   ├── types.ts              # tipos espelhando Pydantic schemas
│       │   ├── stores/{user,settings}.ts   # estado global
│       │   └── components/
│       │       ├── Table.svelte      # tabela genérica com slot de ações
│       │       ├── Form.svelte       # form com eyebrow + título + submit
│       │       ├── Card.svelte / Funnel.svelte / Pie.svelte  # viz do dashboard
│       └── routes/
│           ├── +layout.svelte/.ts    # header com branding, carrega /auth/me + /settings
│           ├── +page.svelte          # Dashboard
│           ├── login/+page.svelte
│           ├── quotes/{,new,[id]}/+page.svelte
│           ├── inbox/+page.svelte
│           ├── clients,materials,services,spools,settings/+page.svelte
│           └── static/manifest.webmanifest, icons
│
├── migrations/                       # Alembic
│   ├── env.py
│   └── versions/
│       ├── 0001_baseline.py                  # cria as 11 tabelas
│       └── 0002_qi_material_nullable.py      # quote_items.material_version_id nullable
│
├── tests/e2e/                        # Playwright (happy path)
├── docs/superpowers/                 # spec + plano (autoritativos)
├── docker-compose.yml                # db + api
├── Dockerfile                        # python:3.12-slim + WeasyPrint deps nativas
├── Makefile                          # atalhos
├── pyproject.toml
└── playwright.config.ts
```

**Regra de dependência (crítica):** `api → core`, `infra → core`. **`core` não importa de `api` nem de `infra`.** Isso é o que torna o domínio testável sem DB e migrável pra qualquer plataforma (Lambda, ECS, lift-and-shift) sem reescrever lógica.

---

## Modelo de dados

11 tabelas. Diagrama lógico:

```
User ───┐
        │ cria
        ▼
   Quote ──── client_id ──→ Client
     │
     ├── items ──→ QuoteItem ── material_version_id ──→ MaterialVersion (SCD2)
     │                │
     │                └── consumptions ──→ MaterialConsumption ── spool_id ──→ Spool
     │
     └── services ──→ QuoteService ── service_id ──→ Service

Settings (singleton)
WatcherInboxFile  ── opt quote_id ──→ Quote
```

### Detalhes por tabela

| Tabela | Chaves & decisões |
|---|---|
| `users` | id UUID, email único, password_hash (argon2id) |
| `clients` | id UUID, nome obrigatório, sem soft-delete no MVP |
| `material_versions` | **SCD2**: `effective_from`/`effective_to`/`is_current`. PUT cria nova versão e fecha a atual. `failure_rate_pct` por material. Snapshot natural via FK + imutabilidade da versão. |
| `services` | catálogo reutilizável. `kind ∈ {labor, purge, other}`. `unit ∈ {min, hour, g}`. |
| `spools` | rolo físico comprado: `purchased_price`, `initial_grams`, `remaining_grams`, status `open/empty/discarded`. |
| `settings` | **singleton** (PK fixo `id=1`). `energy_kwh_price`, `printer_power_w`, `printer_depreciation_per_hour`, `currency`, **`business_name` / `business_tagline` / `logo_path` / `brand_color_primary`** (branding), `stalled_quote_alert_days`, `low_spool_threshold_g`. |
| `quotes` | `kind ∈ {commercial, personal}`, `client_id` (nullable se personal), `status`, `markup_pct`, `min_charge`, timestamps por estado (`finalized_at`, `approved_at`, `produced_at`, `delivered_at`, `cancelled_at`). |
| `quote_items` | 1 peça do orçamento. `gcode_meta` JSONB (`{time_s, filament_m, material, machine}`), `material_version_id` (**nullable** desde 0002 — item pode entrar pendente), `quantity`, overrides opcionais (`depreciation_rate_override`, `failure_rate_override`). |
| `quote_services` | linhas de serviço aplicadas; `rate` é **snapshot** (não muda quando o catálogo mudar). |
| `material_consumptions` | fato de consumo na **produção**: `quote_item_id`, `spool_id`, `grams_used`, `unit_cost_snapshot`. Permite custo orçado vs real. |
| `watcher_inbox_files` | `file_hash` único (sha256) → idempotência; `status ∈ {pending, assigned, discarded}`. |

**Por que SCD2 em Material e não em Spool?** Material varia preço/densidade no tempo (regional, fornecedor) — quero histórico. Spool já tem ciclo de vida natural (`open → empty`), não precisa de SCD2.

---

## Domínio e fluxos

### Fórmula de custo (por peça)

```
filamento  = grams_from_meters(filament_m, density, 1.75mm) × price_per_kg / 1000
energia    = power_w × (time_s/3600) / 1000 × kwh_price
depreciação = (time_s/3600) × rate_per_hour
base       = filamento + energia + depreciação
com_falha  = base × (1 + failure_pct/100)
subtotal   = com_falha × quantity
```

### Fórmula do orçamento

```
custo  = Σ(subtotal_items) + Σ(quantity × rate)_services
total  = max(custo × (1 + markup_pct/100), min_charge)   ← só para commercial
```

Para `personal`, exibe **custo total** (sem markup, sem min_charge, sem mão de obra).

### Workflow

```
COMMERCIAL:
draft ─finalize→ orcado ─approve→ aprovado ─produce→ produzido ─deliver→ entregue
   │                │                  │
   └──── cancel ────┴──── cancel ──────┘    (qualquer estado pré-entregue)

PERSONAL (encurtado):
draft ─finalize→ produzido
   │
   └── cancel
```

- **finalize** congela o orçamento (status sai de `draft`, vira `orcado` ou `produzido` em personal).
- **produce** recebe um payload `{consumption: [{quote_item_id, spool_id}, ...]}`, debita gramas de cada spool e cria 1 linha de `MaterialConsumption` por item com `unit_cost_snapshot = spool.purchased_price / spool.initial_grams`.
- **personal → approve** → 400. Tentar `produce` em personal → 400. Validação garante integridade dos estados por `kind`.
- **labor service** em quote `personal` → 400.

### Material pendente (workflow novo)

Quando um gcode declara um material não cadastrado, o item é aceito **pendente** (badge amarelo + `material_version_id NULL`). O `finalize` retorna 409 enquanto houver pendentes. O usuário pode:

1. Cadastrar o material em `/materials` (ou no modal de resolução), e
2. Aplicar via `PUT /quotes/{id}/items/{item_id}` com `{ material_code }`.

### Watcher

- Tarefa asyncio iniciada no `startup` do FastAPI **se** `WATCH_DIR` estiver setado.
- Usa `watchfiles.awatch` para reagir a `*.gcode` novos.
- Hash sha256 garante idempotência: o mesmo arquivo nunca cria dois `WatcherInboxFile`.
- Cria entrada `pending`; usuário decide promover (vira `Quote draft` + `QuoteItem`) ou descartar.

---

## API

| Método/Path | Notas |
|---|---|
| `POST /auth/login` | Body `{email, password}`. Seta cookie `session` HttpOnly. |
| `POST /auth/logout` | Limpa cookie. |
| `GET /auth/me` | Retorna `{id, name, email}` do usuário logado. |
| `GET /healthz` | Liveness — único endpoint sem auth (além do login). |
| `GET\|POST /clients` & `/clients/{id}` | CRUD simples; PUT é parcial; DELETE hard. |
| `POST /materials` | Cria novo material com **versão inicial** SCD2. |
| `GET /materials` | Lista apenas versões `is_current=true`. |
| `GET /materials/{code}` & `/history` | Versão atual / histórico completo. |
| `PUT /materials/{code}` | **Encerra versão atual + cria nova.** |
| `DELETE /materials/{code}` | Só se nunca foi referenciado por QuoteItem (senão 409). |
| `GET\|POST /services` & `/services/{id}` | CRUD; `kind=labor/purge/other`. |
| `GET\|POST /spools` & `PUT /spools/{id}` | Inventário; valida `remaining_grams ≤ initial_grams`. |
| `GET /settings` / `PUT /settings` | Singleton; ignora keys não enviadas. |
| `POST /settings/logo` (multipart) | Upload PNG/JPG/SVG → `storage/branding/logo.<ext>`. |
| `DELETE /settings/logo` | Remove arquivo e zera `logo_path`. |
| `GET /settings/logo` | Serve a imagem (FileResponse). **Sem auth — asset público.** |
| `POST /quotes` | Cria draft com `{kind, client_id?, markup_pct, min_charge}`. |
| `GET /quotes?status=&kind=&client_id=` | Lista com filtros. |
| `GET\|PUT\|DELETE /quotes/{id}` | PUT só em `draft`. |
| `POST /quotes/{id}/items` (multipart) | Upload `.gcode`; aceita pendente se material desconhecido. |
| `PUT /quotes/{id}/items/{item_id}` | Edita `name/quantity` e **resolve material pendente** via `material_code`. |
| `DELETE /quotes/{id}/items/{item_id}` | Só em draft. |
| `POST\|DELETE /quotes/{id}/services[/{qs_id}]` | Idem; valida labor em personal. |
| `POST /quotes/{id}/transitions/{finalize\|approve\|produce\|deliver\|cancel}` | Cada um valida o `kind` e o `status` atual. |
| `GET /quotes/{id}/pdf` | Renderiza HTML → PDF, com branding do `/settings`. Headers de download. |
| `GET /inbox` | Lista `WatcherInboxFile` em `pending`. |
| `POST /inbox/{id}/promote` | Body `{kind, client_id?, name?}` → cria Quote+Item. Marca inbox como `assigned`. |
| `DELETE /inbox/{id}` | Marca `discarded`. |
| `GET /dashboard?from=&to=&kind=` | Retorna `{cards, charts, lists}` agregado. |

OpenAPI completo em `http://localhost:8000/docs`.

---

## Frontend — página por página

Todas as páginas (exceto `/login`) requerem cookie de sessão válido. `requireAuth()` em `$lib/guard.ts` redireciona para `/login` se não autenticado. O `+layout.svelte` carrega `/auth/me` + `/settings` no mount e expõe via stores (`$user`, `$appSettings`). Branding (logo, nome, cor primária) é aplicado consistentemente.

### `/login`
Formulário email + senha → `POST /auth/login`. Cookie HttpOnly seta sessão de 7 dias. Em erro de credencial, mostra "credenciais inválidas".

### `/` Dashboard
Consome `GET /dashboard`. Mostra:
- **8 cards** (receita, despesa, lucro, margem%, gasto pessoal, orçamentos por estado, taxa de conversão, estoque g + R$)
- **Funil** (orçado → aprovado → produzido → entregue, SVG inline, sem libs)
- **Pizza/donut** de despesa por categoria (filamento, energia, mão de obra, depreciação) — no MVP entrega zeros até a agregação ser implementada; UI mostra "sem dados"
- **4 listas** (últimos 10 orçamentos, parados, spools com pouco filamento, inbox pendente)

Filtros globais (período + kind + cliente) na própria página, query string repassada ao endpoint.

### `/quotes`
Tabela paginada com filtros. Status como badge colorido. Click no row leva a `/quotes/[id]`. Botão "+ Novo" leva a `/quotes/new`.

### `/quotes/new`
Wizard mínimo: escolha `kind` (radio commercial/personal) → se commercial, mostra dropdown de cliente + inputs de markup% + min_charge. Cria draft via `POST /quotes` e redireciona pra edição.

### `/quotes/[id]` ⭐ a página mais complexa
- **Header**: status badge + kind tag + ID.
- **Painel principal (peças)**:
  - Tabela com nome, **material** (com badge "pendente" se aplicável), filamento, tempo, qtd, subtotal.
  - Em `draft`: form de upload (file + nome + qtd) e botões "remover" / "resolver" (se pendente).
  - Modal **Resolver material pendente**: dropdown de materiais cadastrados ou link "Cadastrar X" que abre form embutido (código + densidade + preço/kg + falha%).
- **Painel de serviços**:
  - Lista de serviços aplicados + form pra adicionar.
  - Em `personal`, esconde serviços com `kind=labor`.
- **Side panel direito**:
  - **Totais**: custo, markup, mínimo, total (commercial) ou custo total (personal).
  - **Ações**: finalize (desabilitado se quantidade=0 ou `pending_items > 0`), approve, produzir (abre modal), deliver, cancel — todos gateados pelo workflow do `kind`.
  - **Metadados**: timestamps de cada transição.
- **Modal "Produzir"**: lista as peças, oferece dropdown de spool por peça (filtrado pelo material). Submit chama `POST /quotes/{id}/transitions/produce`.
- **Botão "Baixar PDF"**: abre `/api/quotes/{id}/pdf` em nova aba.

### `/inbox`
Lista de `WatcherInboxFile` pendentes (gcodes detectados pelo watcher). Para cada um:
- Mostra path original + metadados parseados (tempo, filamento, material detectado).
- Botão **Promover** abre modal: escolhe `kind` + cliente (se commercial) + nome opcional → cria Quote+Item e navega pra ela.
- Botão **Descartar** marca como `discarded`.

### `/clients`
CRUD básico em uma única tela. Form embutido pra criar; lista com Editar (modal) e Excluir (confirmação).

### `/materials`
- Lista das versões `is_current=true`.
- Form de criação (POST = nova entidade).
- Botão "Editar" abre modal — qualquer mudança via PUT cria **nova versão SCD2** (fecha a anterior). UI explica.
- Botão "Histórico" mostra a linha do tempo de versões com `effective_from/to`.
- Excluir só é permitido se nunca foi referenciado em QuoteItem (409 caso contrário; UI surfaces o erro).

### `/services`
CRUD com dropdowns de `kind` (labor/purge/other) e `unit` (min/hour/g). Flag `is_active` controla visibilidade no `/quotes/[id]`.

### `/spools`
Lista de rolos físicos com `remaining_grams` colorido (verde > limiar, amarelo < limiar). Form de criação inclui supplier opcional, lote, data de compra. Editar permite ajuste manual (correção de discrepância).

### `/settings`
- **Identidade visual**: nome do negócio, tagline, cor primária (hex), moeda. Upload + preview de logo (PNG/JPG/SVG). Botão "Remover logo".
- **Custo de produção**: tarifa kWh, potência média da impressora, depreciação por hora.
- **Alertas**: dias para alerta de orçamento parado, gramas para alerta de spool baixo.
- Botão único "Salvar todas as alterações" submete o PUT consolidado.

---

## Nuances importantes

### 1. Branding configurável é fim-a-fim
Logo + nome + cor primária no `/settings` afetam: header do webapp, `<title>` da aba, manifest PWA (ícone na home do celular), header e rodapé do PDF. Quando você decidir o nome/logo da marca, basta upload — nenhum refactor.

### 2. SCD2 em Material não é academia — é necessidade
Quando você muda o preço do PLA hoje, **orçamentos antigos não devem mudar de valor**. A FK `QuoteItem.material_version_id` aponta para a versão imutável da hora da emissão. Você consegue auditar "esse orçamento foi feito com PLA a R$110, mas o preço atual é R$130".

### 3. Material pendente em vez de erro 400
Se o gcode declara um material desconhecido, o backend cria o item pendente em vez de rejeitar. O `finalize` é bloqueado até resolver. Isso evita o atrito "tenho que cadastrar antes de fazer upload".

### 4. Snapshot em QuoteService.rate
Tarifa do serviço gravada no `QuoteService.rate` no momento da emissão. Se você editar o catálogo depois, orçamentos antigos não mudam.

### 5. Custo real vs orçado
- Ao **orçar**, o sistema usa `MaterialVersion.price_per_kg_ref` (preço de referência do catálogo).
- Ao **produzir**, debita do `Spool` físico e grava `unit_cost_snapshot = spool.purchased_price / spool.initial_grams` no `MaterialConsumption`.
- O dashboard pode comparar **receita** (orçamento aprovado) vs **despesa real** (consumo + energia + serviços).

### 6. EmailStr exige domínio com ponto
Pydantic rejeita `usuario@local`. Use `@local.app` ou um TLD real. Se você precisar de emails sem domínio (apenas identificador interno), troque `EmailStr` por `str` em `users.py` e `auth.py`.

### 7. Testes usam DB separado (`app_test`)
`make test` derruba e recria `app_test` automaticamente, aplica migrações e roda a suíte. **Seu DB `app` (dev) fica intocado**. Antes da versão de 2026-06-07 isso não era o caso e rodar pytest apagava dados — agora está corrigido em `backend/tests/conftest.py`.

### 8. Watcher é opcional
Se `WATCH_DIR` não estiver setado no `.env`, o watcher não inicia. Não há erro nem warning. Bom para dev local sem precisar montar pasta no container.

### 9. CORS desnecessário em dev
O Vite faz proxy de `/api/*` para `localhost:8000`, então o browser sempre vê origem única (`localhost:5173`). Sem cross-origin → sem CORS → sem dor de cabeça. Em prod, se separar host do frontend e da API, ajustar `CORS_ORIGINS` no `.env`.

### 10. Cookie HttpOnly + SameSite=Lax
Cookie de sessão (`session`) é HttpOnly (JS não vê), SameSite=Lax (não vaza em cross-site GET pesado). `Secure` está desligado em DEV (HTTP). Em prod, setar `Secure=True` exige HTTPS — não esquecer.

### 11. Race condition do `git add -A` durante Wave 1
Durante a implementação inicial, dois subagentes rodando em paralelo fizeram `git add -A` simultaneamente, misturando arquivos do frontend num commit do core. Está documentado no histórico; sem impacto funcional, só estética dos commits.

### 12. Material pendente preserva `gcode_meta.material`
Quando um item é resolvido via `PUT /quotes/{id}/items/{item_id}` com `material_code`, o `gcode_meta.material` é atualizado para o código escolhido. Assim a tabela na UI não mostra mais o código antigo "pendente" depois do refresh.

---

## Testes

### Backend

```bash
make test
```

Roda **46 testes** pytest em ~7s. Categorias:

| Pasta | Cobre |
|---|---|
| `backend/tests/core/` | parser gcode, fórmulas de custo, agregação de quote (pure functions) |
| `backend/tests/infra/` | render PDF, watcher (scan_once + idempotência) |
| `backend/tests/api/` | endpoints completos via ASGI (httpx + cookie auth) |

Estratégia de isolamento:
- DB **separado** (`app_test`) criado/migrado por sessão.
- Cada teste recebe **um engine NullPool novo** (evita "Future attached to a different loop").
- Cleanup autouse trunca todas as tabelas entre testes (ordem FK-safe).
- Fixture `auth_client` cria usuário `t@t.com/pw` no DB de teste e já entrega cookie logado.

### E2E (Playwright)

```bash
make e2e-install    # 1ª vez: @playwright/test + chromium
make seed           # garante usuário dev em app
make e2e            # roda happy path
```

`tests/e2e/happy_path.spec.ts`: login → upload gcode → finalize → baixa PDF.

---

## Deploy / LAN

O serviço foi pensado pra rodar:

1. **No seu Mac/PC durante uso** (compose up + `npm run dev`).
2. **No Raspberry Pi Zero 2W ou similar** (mesmo compose; possivelmente apertado, plano B é PC).
3. **AWS futuramente** (ECS Fargate + RDS Postgres + S3 para storage, ou Lambda + DynamoDB com adapter trocado em `infra/`).

### Expor na LAN da casa

Para a esposa/funcionários acessarem do celular:

```bash
make fe-dev   # já escuta em 0.0.0.0 por padrão se passar --host
# ou:
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173
```

Pegue o IP do Mac (`ipconfig getifaddr en0`) e compartilhe:

```
http://<IP-DO-MAC>:5173
```

Macs com firewall ativado podem pedir permissão na primeira conexão inbound.

### Variáveis de ambiente

| Variável | Default | Para que |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://app:app@db:5432/app` | Postgres principal |
| `SESSION_SECRET` | `change-me-in-prod` | **Mudar em prod**; usado pra assinar JWT |
| `WATCH_DIR` | `/data/watch` | Watcher só inicia se setado |
| `STORAGE_DIR` | `/data/storage` | Gcodes + logo |
| `CORS_ORIGINS` | `http://localhost:5173` | CSV; só importa se frontend e API forem hosts diferentes |
| `PWD_ARGON2_TIME_COST` | `2` | Tunável caso quera mais resistência |
| `PWD_ARGON2_MEMORY_COST` | `65536` | Bytes |

---

## Backlog (pós-MVP)

Itens do spec §14 que ficaram fora do MVP de propósito:

- Aprovação online pelo cliente via link público com token
- Notificações (WhatsApp/email)
- Versionamento auditável do `Settings`
- Multi-tenant
- Integração direta com Klipper/Moonraker (puxar jobs da impressora)
- Estoque por cor dentro de um spool
- Suporte a outros slicers (PrusaSlicer, OrcaSlicer, Bambu Studio) — começa por Creality Print, dialect-driven em `core/gcode/dialects.py`
- Mobile app nativo
- Agregação real de `receita_vs_despesa` e `orcado_vs_real` (charts G1, G6 do dashboard)
- Pagamento integrado
- Deploy AWS (ECS/Fargate + RDS + S3 + CloudFront)
