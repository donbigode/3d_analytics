# 3D Print Orçamento & Analítico

MVP de orçamento e analítico para uma operação pessoal de impressão 3D.

- **Backend:** FastAPI + Postgres (Alembic, SQLAlchemy 2 async).
- **Frontend:** SvelteKit (adapter-static, PWA), proxy Vite para `/api`.
- **Autenticação:** argon2id + cookie JWT (sem self-signup).
- **Watcher:** olha uma pasta em busca de `.gcode` e cria entradas no inbox.
- **PDF:** WeasyPrint com o mesmo branding configurável no `/settings`.

## Quick start

```bash
cp .env.example .env       # ajuste SESSION_SECRET pelo menos
make up                    # docker compose: api + postgres + migrações
make create-user           # cria o primeiro usuário (interativo)
open http://localhost:8000 # web app (vite dev em http://localhost:5173)
```

Em desenvolvimento, rode o frontend separadamente para hot-reload:

```bash
make fe-install
make fe-dev    # http://localhost:5173 (proxy /api → :8000)
```

## Testes

```bash
make test       # backend (pytest, ~46 testes)
make e2e        # Playwright happy path (requer make up + make seed antes)
```

A primeira execução de E2E precisa de:

```bash
make e2e-install   # instala @playwright/test + chromium
make seed          # cria usuário t@t.com / pw (idempotente)
make e2e
```

## Estrutura

```
backend/        FastAPI (api/, core/, infra/)
frontend/       SvelteKit
migrations/     Alembic
tests/e2e/      Playwright
docs/superpowers/  spec + plano de implementação
```

## Páginas

- `/` dashboard (cards C1–C8 + funil + pizza de despesa + listas L1–L4)
- `/quotes`, `/quotes/new`, `/quotes/[id]` (lista, criação, edição+transições+PDF)
- `/inbox` (arquivos do watcher; promover ou descartar)
- `/clients`, `/materials`, `/services`, `/spools`, `/settings`

## Notas

- A primeira `make up` aplica as migrações automaticamente.
- Logo e branding (`business_name`, `brand_color_primary`) são configurados em `/settings` e refletem no header, PDF e PWA.
- Sem multi-tenant; sem link público de orçamento. Veja `docs/superpowers/specs/` para detalhes.
