# 3D Print Orçamento & Analítico — Design Doc

**Data:** 2026-06-06
**Status:** spec aprovado (aguardando user review)
**Autor:** brainstorm Otavio + Claude

---

## 1. Objetivo

Construir um serviço web (rodando inicialmente na rede local da oficina/casa, com migração futura para microsserviço AWS) que:

1. Extrai metadados de arquivos `.gcode` produzidos por slicers (começando por Creality Print) e calcula **custo de produção real e detalhado** de cada impressão.
2. Aplica regras de **preço de venda** (filamento + energia + mão de obra + depreciação + taxa de falha + markup) para gerar **orçamentos** para clientes.
3. Mantém **catálogo, inventário (com SCD2) e consumo real** de filamento, permitindo comparar custo orçado vs custo real.
4. Rastreia o **ciclo de vida** de cada trabalho (orçado → aprovado → produzido → entregue), distinguindo trabalhos comerciais de projetos pessoais (despesa).
5. Apresenta um **analítico** (dashboard) com saúde financeira, conversão, consumo de material e variância orçado-vs-real.

Usuários do MVP: Otavio + esposa (~2 usuários). Acesso via web (PC + celular), na mesma rede local. PWA para uso fluido no celular.

## 2. Não-objetivos (fora do MVP)

- Multi-tenant / multi-oficina.
- Auto-cadastro / portal público do cliente / aprovação online.
- Integração direta com impressora (Klipper/Moonraker).
- Permissões granulares (RBAC). Todo usuário pode tudo.
- Versionamento auditável de `Settings`.
- Notificações (e-mail, WhatsApp, push) — saída do PDF é manual.
- Pagamento integrado.
- Mobile app nativo (PWA cobre).
- Estoque rateado por cor dentro de um spool.

## 3. Stack e arquitetura

### 3.1 Stack

| Camada | Tecnologia |
|---|---|
| Linguagem backend | Python 3.12 |
| Framework web | FastAPI |
| ORM / DB | SQLAlchemy 2.x async + asyncpg |
| Banco | PostgreSQL 16 (container) |
| Migrations | Alembic |
| Auth | sessão via cookie HttpOnly, senha hash com argon2id |
| PDF | WeasyPrint (HTML → PDF) |
| Watcher | `watchfiles` em asyncio task |
| Frontend | SvelteKit (adapter-static) + PWA |
| Containers | Docker + docker-compose |
| Testes | pytest, httpx, testcontainers, Playwright (1 E2E) |

### 3.2 Estrutura de pacotes

```
3d_analytics/
├── backend/
│   ├── core/                    # domínio puro, zero deps de framework
│   │   ├── gcode/
│   │   │   ├── parser.py        # extrai TIME, Filament, Material, Machine
│   │   │   └── dialects.py      # Creality / Prusa / Orca / Bambu (futuro)
│   │   ├── pricing/
│   │   │   ├── cost.py          # filamento + energia + depreciação
│   │   │   ├── labor.py         # serviços do catálogo
│   │   │   ├── failure.py       # taxa de falha por material
│   │   │   └── quote.py         # markup + mínimo → preço de venda
│   │   └── models.py            # dataclasses Pydantic do domínio
│   │
│   ├── infra/                   # adapters trocáveis (interfaces no core)
│   │   ├── db/                  # SQLAlchemy: engine, sessões, repositórios, Alembic
│   │   ├── storage/             # filesystem (gcodes + branding)
│   │   ├── pdf/                 # WeasyPrint + templates HTML
│   │   └── watcher/             # asyncio task que olha WATCH_DIR
│   │
│   ├── api/                     # FastAPI: só transporte HTTP
│   │   ├── routes/              # auth, quotes, clients, materials, services, spools, settings, dashboard
│   │   ├── schemas/             # Pydantic request/response
│   │   └── deps.py              # autenticação, sessão DB
│   │
│   ├── app.py                   # entrypoint FastAPI
│   └── settings.py              # config (env vars)
│
├── frontend/                    # SvelteKit static + PWA
│   └── src/routes/
│
├── docs/superpowers/specs/      # este arquivo e futuros
├── docker-compose.yml
├── Makefile
└── .env.example
```

**Regra de dependência (importa):** `api → core`, `infra → core`. `core` **não** importa nada de `api` ou `infra`. Toda I/O em `infra/` via interfaces declaradas em `core/` (Repository pattern). Isso permite testar o domínio sem DB e migrar pra microsserviço AWS sem reescrever lógica.

## 4. Modelo de dados

### 4.1 Entidades principais

| Entidade | Campos chave |
|---|---|
| `User` | id, name, email, password_hash, created_at |
| `Client` | id, name, phone, email, notes, created_at |
| `MaterialVersion` (SCD2) | id, material_code (PLA, PETG…), name, density_g_cm3, price_per_kg_ref, failure_rate_pct, effective_from, effective_to, is_current |
| `Service` | id, name, unit (min/hour/g), default_rate, kind (`labor`/`purge`/`other`), is_active |
| `Spool` | id, material_code, supplier, batch_code, purchased_at, purchased_price, initial_grams, remaining_grams, status (open/empty/discarded), notes |
| `Settings` (singleton) | energy_kwh_price, printer_power_w, printer_depreciation_per_hour, currency, business_name, business_tagline, logo_path, brand_color_primary, stalled_quote_alert_days, low_spool_threshold_g |
| `Quote` | id, kind (`commercial`/`personal`), client_id (nullable se personal), user_id, status, markup_pct, min_charge, notes, created_at, finalized_at, approved_at, produced_at, delivered_at, cancelled_at |
| `QuoteItem` | id, quote_id, name, filename, gcode_meta (JSONB), material_version_id, quantity, depreciation_rate_override (nullable), failure_rate_override (nullable) |
| `QuoteService` | id, quote_id, service_id, quantity, rate (snapshot) |
| `MaterialConsumption` | id, quote_item_id, spool_id, grams_used, consumed_at, unit_cost_snapshot |
| `WatcherInboxFile` | id, file_hash, original_path, parsed_meta (JSONB), status (pending/assigned/discarded), quote_id (nullable), created_at |

### 4.2 Decisões importantes

1. **`gcode_meta` como JSONB** no `QuoteItem` — guarda `{time_s, filament_m, material_code_detected, machine}`. O `.gcode` bruto fica em `storage/gcodes/<quote_id>/<filename>`.
2. **Snapshot por FK + imutabilidade**: `QuoteItem.material_version_id` aponta para a versão SCD2 da hora da emissão; versões antigas nunca mudam → snapshot natural sem coluna extra.
3. **`QuoteService.rate` snapshot escalar** — `Service` pode mudar; rate gravado preserva o orçamento original.
4. **Taxa de falha por material**, com override opcional por item (`failure_rate_override` em `QuoteItem`, nullable). **Depreciação** vem de `Settings.printer_depreciation_per_hour` aplicada ao `gcode_meta.time_s`; pode ser substituída por item via `QuoteItem.depreciation_rate_override` (nullable, R$/hora). Quando nulo, usa o valor de `Settings`.
5. **Mão de obra e purga compartilham `Service`** diferenciadas por `kind`. `labor` = tempo × rate. `purge` = gramas × rate (custo material). `other` = livre.
6. **`Settings` singleton** sem versionamento no MVP — auditoria de mudança de preço fica pra fase 2.
7. **SCD2 em `MaterialVersion`**: PUT em `/materials/{code}` encerra a current (`effective_to=now()`, `is_current=false`) e cria nova linha current.
8. **`Spool` sem SCD2**: o ciclo de vida (open → empty/discarded) já é histórico suficiente.
9. **`MaterialConsumption`** registra o custo real (do spool, no momento do consumo) — permite analítico de orçado vs real.

## 5. Fluxos principais

### 5.1 Criar orçamento (upload manual)

1. `POST /quotes` com `kind` e `client_id` opcional → cria em status `draft`.
2. `POST /quotes/{id}/items` (multipart `.gcode`) — backend salva arquivo, faz parse, resolve `MaterialVersion` current pelo `material_code` detectado, cria `QuoteItem`, recalcula totais do quote.
3. `POST /quotes/{id}/services` — adiciona linha de serviço. Se `kind=personal`, recusa services `kind=labor` (400).
4. `POST /quotes/{id}/transitions/finalize` — congela snapshots, status vira `orcado` (commercial) ou pula direto pra estado pré-produção (personal).

### 5.2 Watcher de pasta

- `infra/watcher/` registra task asyncio no startup do FastAPI.
- Olha `WATCH_DIR` (env var) via `watchfiles`.
- Para cada `.gcode` novo: calcula hash, ignora se já visto, parseia, cria `WatcherInboxFile` em `pending`.
- Frontend tem rota `/inbox` que lista pendentes. Clicar em "criar orçamento" → cria `Quote` em `draft` + transfere o arquivo + atribui `WatcherInboxFile.quote_id` e status `assigned`.

### 5.3 Transição de estados

**Commercial:**
```
draft ──finalize──► orcado ──approve──► aprovado ──produce──► produzido ──deliver──► entregue
                       │                       │
                       └─── cancel ────────────┘ (qualquer estado pré-produced)
```

**Personal:**
```
draft ──finalize──► produzido            (sem orcado/aprovado/entregue)
            │
            └── cancel
```

Cada transição:
- valida `kind` (rejeita transições inválidas com 400),
- grava `*_at` correspondente,
- em `produce`: dispara o **lançamento de consumo** (passo 5.4).

### 5.4 Produção e consumo de material

- API responde a `POST /quotes/{id}/transitions/produce` com um payload onde, para cada `QuoteItem`, o usuário escolhe o `spool_id` que será debitado (default sugerido: FIFO do material correto entre spools `open`).
- Para cada item: cria `MaterialConsumption(quote_item_id, spool_id, grams_used = gcode_meta.peso × quantity, unit_cost_snapshot = spool.purchased_price / spool.initial_grams)`, debita `spool.remaining_grams`. Se zerar, `spool.status = empty`.
- Tudo em uma transação. Falha se algum spool não tem gramas suficientes (UI deve evitar antes).

### 5.5 Geração de PDF

- `GET /quotes/{id}/pdf` renderiza template Jinja2 (HTML) → WeasyPrint → PDF.
- Mesmo CSS da view web (consistência visual).
- Header do PDF puxa `Settings.business_name`, `Settings.logo_path`, `Settings.brand_color_primary`.
- Para `kind=personal`: PDF gerado como "ficha de custo interna", sem linha "valor a pagar".
- Sem cache no MVP. Download direto pelo dispositivo.

## 6. Branding configurável (logo + nome do negócio)

- Campos em `Settings`: `business_name`, `business_tagline`, `logo_path`, `brand_color_primary`.
- `POST /settings/logo` (multipart, PNG/SVG/JPG) salva em `storage/branding/logo.<ext>`; servido via `/static/branding/logo`.
- `DELETE /settings/logo` volta pro placeholder.
- Locais que usam: header do webapp, `<title>`, manifest PWA, favicon, header e rodapé do PDF.
- Slot já existe em todo template desde o dia 1 — quando você decidir o logo, é só fazer upload sem refactor.

## 7. Projetos pessoais (despesa, sem preço de venda)

- `Quote.kind = personal`:
  - `client_id` nullable.
  - `markup_pct`, `min_charge` ignorados.
  - Workflow encurtado: `draft → produzido`.
  - Serviços de `kind=labor` **escondidos** na UI e rejeitados pela API.
  - Serviços de `kind=purge`/`other` permitidos (têm custo material).
  - PDF = "ficha de custo interna".
  - Dashboard: entra só como despesa (C5).

## 8. APIs (REST/JSON, FastAPI)

### 8.1 Autenticação
- `POST /auth/login` → cookie de sessão
- `POST /auth/logout`
- `GET /auth/me`

### 8.2 CRUDs administrativos
- `GET|POST /clients`, `GET|PUT|DELETE /clients/{id}`
- `POST /materials` cria novo material (novo `material_code`) com versão inicial
- `GET /materials` lista materiais (apenas versões `is_current=true`)
- `GET /materials/{code}` retorna versão current
- `GET /materials/{code}/history` retorna todas as versões
- `PUT /materials/{code}` encerra current e cria nova versão SCD2
- `DELETE /materials/{code}` apenas se nunca foi referenciado (sem `QuoteItem` apontando para nenhuma versão); senão 409. Hard delete remove todas as versões.
- `GET|POST /services`, `GET|PUT|DELETE /services/{id}`
- `GET|POST /spools`, `GET|PUT /spools/{id}`
- `GET|PUT /settings`
- `POST /settings/logo`, `DELETE /settings/logo`
- `GET|POST /users`, `GET|PUT|DELETE /users/{id}`

### 8.3 Fluxo de orçamento
- `POST /quotes` (cria draft com kind, client_id opcional)
- `GET /quotes?status=&kind=&client_id=&from=&to=`
- `GET /quotes/{id}`
- `PUT /quotes/{id}` (só draft)
- `POST /quotes/{id}/items` (multipart `.gcode`)
- `PUT|DELETE /quotes/{id}/items/{item_id}`
- `POST /quotes/{id}/services`
- `DELETE /quotes/{id}/services/{qs_id}`
- `POST /quotes/{id}/transitions/{finalize|approve|produce|deliver|cancel}`
- `GET /quotes/{id}/pdf`

### 8.4 Inbox e dashboard
- `GET /inbox` (lista `WatcherInboxFile` pendentes)
- `POST /inbox/{id}/promote` (vira `Quote`)
- `DELETE /inbox/{id}` (descarta)
- `GET /dashboard?from=&to=&kind=`

## 9. Frontend (SvelteKit, adapter-static, PWA)

### 9.1 Páginas
- `/login`
- `/` dashboard
- `/quotes`, `/quotes/new`, `/quotes/[id]`
- `/inbox`
- `/clients`, `/materials`, `/services`, `/spools`
- `/settings` (inclui upload de logo + branding)
- `/users`

### 9.2 Decisões
- PWA manifest + service worker → "Adicionar à tela inicial" no celular.
- Stores Svelte pra estado global (user, settings).
- Sem state management pesado.
- Forms com validação server-side; frontend só dá feedback imediato.
- Frontend buildado como static; servido pelo próprio FastAPI no MVP (`/` serve `index.html`, `/static/` serve assets). Quando migrar pra AWS pode ir pra S3+CloudFront sem mudar nada.

## 10. Autenticação

- Senha hash com **argon2id** (`argon2-cffi`).
- Sessão = JWT assinado com chave do servidor (`SESSION_SECRET`), gravado em cookie `HttpOnly`, `SameSite=Lax`, `Secure` em prod.
- Expiração 7 dias, renova a cada uso.
- Middleware `require_user` aplica em todas as rotas exceto `/auth/login` e `/healthz`.
- Sem self-signup. Primeiro usuário criado via comando CLI (`python -m backend.cli create-user`).

## 11. Analítico (dashboard MVP)

Filtros globais: período (hoje / 7d / 30d / mês / ano / custom), kind (commercial/personal/ambos), cliente.

### 11.1 Cards
| # | Card | Cálculo |
|---|---|---|
| C1 | Receita comercial | Σ preço venda dos quotes `commercial` com status ≥ `approved` no período |
| C2 | Despesa comercial real | Σ (consumption real + energia + mão de obra) dos quotes `commercial` `produced+` |
| C3 | Lucro líquido | C1 − C2 |
| C4 | Margem média | C3 / C1 × 100 |
| C5 | Gasto em projetos pessoais | Σ custo de quotes `personal produced` |
| C6 | Orçamentos por estado | total + breakdown por estado |
| C7 | Taxa de conversão | `approved / orcado` (%) |
| C8 | Estoque atual | Σ remaining_grams + R$ estimado (Σ remaining_grams × custo unitário do spool) |

### 11.2 Gráficos
| # | Gráfico |
|---|---|
| G1 | Linha do tempo: receita vs despesa (semanal/mensal) |
| G2 | Funil: orçado → aprovado → produzido → entregue |
| G3 | Pizza: despesa por categoria (filamento, energia, mão obra, depreciação) |
| G6 | Orçado vs real por orçamento (% de variância) |

### 11.3 Listas / alertas
- L1: últimos 10 orçamentos
- L2: orçamentos parados em `approved` há mais de `Settings.stalled_quote_alert_days` (default 7)
- L3: spools com `remaining_grams` abaixo de `Settings.low_spool_threshold_g` (default 100g)
- L4: inbox do watcher

## 12. Deploy (Docker + Postgres)

```
docker-compose.yml
├── db    postgres:16-alpine + volume persistente
├── api   build do backend; depends_on db; expõe :8000
└── web   (opcional) build do frontend; no MVP pode ser servido pela própria api
```

- `.env`: `DATABASE_URL`, `SESSION_SECRET`, `WATCH_DIR`, `STORAGE_DIR`, `CORS_ORIGINS`.
- Entrypoint do `api`: `alembic upgrade head` antes de subir Uvicorn.
- Healthcheck: `GET /healthz` → 200.
- `Makefile`: `make up`, `make down`, `make logs`, `make seed`, `make test`, `make create-user`.

## 13. Estratégia de testes

| Camada | Ferramenta | Escopo |
|---|---|---|
| Unit (`core/`) | pytest | Parser, cálculo de custo, regras de transição, SCD2, escolha FIFO. **TDD obrigatório**. |
| Integration (`infra/`) | pytest + testcontainers Postgres | Repositórios, migrations, watcher com tmp dir. |
| API | pytest + httpx | Auth, fluxos de quote, transições inválidas, validação personal vs commercial. |
| E2E | Playwright (1 fluxo) | login → upload gcode → finalize → ver PDF. |

CI: `make test` localmente; GitHub Actions opcional no MVP.

## 14. Backlog (fase 2+)

- Aprovação online pelo cliente via link público com token.
- Notificações (WhatsApp via API, e-mail).
- Versionamento auditável de `Settings`.
- Multi-tenant para outras oficinas.
- Integração Klipper/Moonraker (puxar jobs direto da impressora).
- Estoque por cor dentro de um spool.
- Suporte a outros slicers (PrusaSlicer, OrcaSlicer, Bambu Studio) — começa por Creality Print, dialect-driven em `core/gcode/dialects.py`.
- Mobile app nativo (se PWA não bastar).
- Alertas proativos (e-mail/push) baseados em L2/L3.
- Pagamento integrado.
- Migração para AWS (ECS/Fargate + RDS Postgres + S3 para storage + CloudFront para frontend).

## 15. Riscos / pontos de atenção

- **Estimativa de potência** da impressora (`printer_power_w`) é o número mais incerto — sugerir o usuário medir com wattímetro e atualizar `Settings`.
- **Taxa de falha por material** é estimada — calibrar com dados reais depois de meses de uso (orçado vs real do G6 vai mostrar).
- **WeasyPrint** tem dependências de sistema (cairo, pango) — o Dockerfile precisa instalar pacotes apt; documentar no README.
- **Pi Zero 2W** pode não ser suficiente com Postgres + FastAPI + frontend. Plano B já documentado: rodar num PC qualquer. Não é piso duro.
- **SCD2 em `MaterialVersion`** exige cuidado com FK: nunca permitir hard delete; sempre encerrar versão. Validação no repositório.
