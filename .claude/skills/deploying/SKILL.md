---
name: deploying
description: Use when shipping/subindo a change to production for 3d_analytics, when a deploy run failed, when a deployed change "não apareceu"/isn't visible, or when the Lightsail server is out of disk ("no space left on device").
---

# Deploying 3d_analytics

## Overview

Prod is a single **AWS Lightsail** box running `docker-compose.prod.yml` behind **Caddy**.
A push to `main` triggers `.github/workflows/deploy.yml` in two jobs:
1. **build** (GitHub runner): builds `api` + `frontend` for `linux/amd64` and pushes to GHCR as
   `ghcr.io/donbigode/3d_analytics-{api,frontend}:<sha>` and `:latest`.
2. **deploy**: SSHes to the server, `git pull`s, then runs `/opt/3d-analytics/deploy/deploy.sh`
   (ghcr login → `compose pull` → `alembic upgrade head` → `up -d` → logout → prune).

**The server never builds.** It's a `nano_3_0` (512 MB) after the micro → nano migration (`infra/README.md`).

**Core flow:** branch → PR → merge to `main` → deploy auto-fires → watch run → verify conclusion.

## The standard flow (what we do every time)

Pre-flight (local, via Docker — start it with `open -a Docker` if down):
```bash
docker compose run --rm api pytest backend/tests -q          # all green
cd frontend && npm run check                                  # no NEW errors (library/spools are pre-existing)
docker compose run --rm api ruff check <changed backend files>
```

Ship:
```bash
git push -u origin <branch>
gh pr create --base main --head <branch> --title "..." --body "..."
gh pr merge <PR#> --merge          # triggers the deploy (push to main)
git checkout main && git pull --ff-only
git branch -d <branch> && git push origin --delete <branch>
```

Watch the deploy (push to main fires it):
```bash
sleep 4
gh run list --workflow=deploy.yml --limit 1 --json databaseId,status,event --jq '.[0]'
gh run watch <run_id> --exit-status --interval 15
gh run view <run_id> --json status,conclusion --jq '{status,conclusion}'   # ALWAYS confirm — don't trust watch alone
```

Manual re-deploy (no code change needed — `workflow_dispatch` is enabled):
```bash
gh workflow run deploy.yml ; gh run list --workflow=deploy.yml --limit 1
```

## Prod facts (so diagnostics make sense)

- Compose file: **`docker-compose.prod.yml`** (not the dev one). App lives at **`/opt/3d-analytics`**.
- Services: `db` (pgvector), `api` (uvicorn :8000), `frontend` (build-only), `caddy` (:80/:443).
- Caddy routes **`/api/*` → `api:8000`** (strips `/api`); everything else is the SPA.
- The SPA is served from a **named volume `frontend_build`**. Docker only seeds a named volume when empty, so the frontend image's `CMD` **wipes and recopies** `/build → /srv/frontend` on every container start. ⇒ a deploy that **recreates the frontend container** publishes the new bundle. Look for `Container 3d-analytics-frontend-1 Recreated/Started` in the run log.
- `frontend.url` in the app uses `/api/...`; tests/curl on the server hit `api:8000/...` directly (no `/api`).
- **Produção é só CRUD: sem `[dev]` e sem `[ai]`.** `EXTRAS=""` em dois lugares que precisam andar juntos: `build-args` no `deploy.yml` (é o que vale) e `args` no `docker-compose.prod.yml` (plano B de build na caixa). O default do `Dockerfile` é `[dev,ai]`, que é o que o `docker-compose.yml` local usa pra `pytest`/`ruff`.
- Sem `[ai]`, não há torch/sentence-transformers nem SDKs de LLM: `factory.py` pula providers cujo SDK falta (cai no "nenhum provider configurado") e `embeddings.py` levanta `EmbeddingsUnavailable`. Features de LLM/trends-sugestões respondem como "sem provider" — esperado, não bug.
- Com `[ai]` (dev), torch vem do índice CPU e o `RUN test ! -d .../site-packages/nvidia` **quebra o build** se a stack CUDA voltar. Se falhar nessa linha, não remova a guarda: descubra qual bump reinstalou torch pelo PyPI.
- Pacotes GHCR ligados ao repo pela label `org.opencontainers.image.source`; o deploy faz pull com o `GITHUB_TOKEN` efêmero do job. Pra rodar `deploy.sh` à mão com pacote privado, passe `GHCR_USER`/`GHCR_TOKEN` (PAT com `read:packages`).
- **Um deploy por vez** (`concurrency: deploy-prod`, `cancel-in-progress: false`). Dois merges próximos enfileiram em vez de rodar juntos. Se você mergear dois PRs seguidos, o segundo run fica `queued` até o primeiro terminar — isso é o desenho, não travamento. Nunca mude para `cancel-in-progress: true`: cancelar no meio deixa a caixa com imagem nova construída, containers na versão velha e migração talvez aplicada.

## Common failures & fixes

| Symptom | Cause | Fix |
|---|---|---|
| Run fails: `no space left on device` | Lightsail disk full | Raro desde que o build saiu da caixa (imagem da api só-CRUD é pequena). `deploy.sh` faz `image prune -af` + `builder prune -af` depois do `up` e imprime `df -h`. Se acontecer: SSH + `docker system prune -af` (**sem** `--volumes`: `frontend_build`/`caddy_data` são volumes nomeados) |
| `deploy` job: `denied`/`unauthorized` no pull | Pacote GHCR não ligado ao repo | Conferir a label `org.opencontainers.image.source` no job `build`, ou em GitHub → Packages → o pacote → *Manage Actions access* adicionar o repo |
| Container `api` em crashloop logo após deploy com `ModuleNotFoundError` | Import de lib do `[ai]` fora de import lazy | O import sweep do `Dockerfile` deveria pegar no build; mover o import pra dentro da função e tratar `ImportError` |
| Run = success but change **"não apareceu"** | Your **browser** cached the old SPA (server is fresh) | Hard refresh **Cmd/Ctrl+Shift+R** or incognito |
| A list shows nothing | **Empty state**, no seed (e.g. people) | Add data in the UI — not a bug |
| Segundo deploy fica `queued` por minutos | `concurrency: deploy-prod` enfileirando — esperado após dois merges seguidos | Esperar. Conferir com `gh run list --workflow=deploy.yml --limit 3` |
| `gh run watch` returned but unsure | watch can exit early/stale | Confirm with `gh run view <id> --json conclusion` |

## On-server diagnostics (when a deploy "didn't take")

SSH as the deploy user, then at `/opt/3d-analytics`:
```bash
git config --global --add safe.directory /opt/3d-analytics   # silence "dubious ownership"
git log --oneline -1                                         # is the new commit checked out?
docker compose -f docker-compose.prod.yml run --rm api alembic current   # expect the head revision
df -h                                                        # disk headroom

# Is the NEW frontend actually served? grep a string unique to the change:
docker compose -f docker-compose.prod.yml exec -T caddy sh -c "grep -rl '<unique UI string>' /srv/frontend | wc -l"   # ≥1 = new bundle live

# Does a backend route exist? (401 = exists, just needs auth; 404 = backend not updated)
docker compose -f docker-compose.prod.yml exec -T caddy wget -S -O /dev/null http://api:8000/<route> 2>&1 | grep -i 'HTTP/'
```
Run multiline `python -c` as a **single line** over SSH — pasted indentation causes `IndentationError`.

## Verdict logic

- `alembic current` = head **and** frontend grep ≥ 1 ⇒ prod is up to date → it's **browser cache** or **empty state**, not a deploy problem.
- frontend grep = 0 ⇒ the new SPA isn't served → re-deploy (and check the run recreated the frontend container).
- route = 404 ⇒ backend image is stale → re-deploy / check the `build` job pushed `:<sha>` (`docker compose -f docker-compose.prod.yml images` on the box shows the tag in use).

## Notes

- Each change has been: small branch → PR → squash-less `--merge` → watch → verify. Keep that cadence.
- Build runs on the GitHub runner with `type=gha` layer cache; the SSH step only pulls, so `command_timeout` is 10m.
- This is a **project runbook**, not a discipline skill — update it whenever the prod topology or deploy script changes.
