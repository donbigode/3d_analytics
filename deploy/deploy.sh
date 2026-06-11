#!/usr/bin/env bash
# deploy/deploy.sh — usado pelo GitHub Actions e disponível pra rodar
# manualmente via SSH no servidor. Idempotente.
set -euo pipefail

cd /opt/3d-analytics

echo "==> git pull"
git pull --ff-only origin main

echo "==> build images"
docker compose -f docker-compose.prod.yml build api frontend

echo "==> migrate"
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

echo "==> up"
docker compose -f docker-compose.prod.yml up -d

echo "==> prune dangling images"
docker image prune -f

echo "==> done"
