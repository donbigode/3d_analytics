#!/usr/bin/env bash
# deploy/deploy.sh — usado pelo GitHub Actions e disponível pra rodar
# manualmente via SSH no servidor. Idempotente.
#
# As imagens são construídas no GitHub Actions e publicadas no GHCR; aqui só
# fazemos pull. IMAGE_TAG (sha do commit) vem do workflow; rodando à mão sem
# ele, usa `latest`. GHCR_USER/GHCR_TOKEN só são necessários se o pacote no
# GHCR for privado — o workflow sempre passa um token efêmero do job.
set -euo pipefail

cd /opt/3d-analytics

export IMAGE_TAG="${IMAGE_TAG:-latest}"
COMPOSE="docker compose -f docker-compose.prod.yml"

echo "==> git pull"
git pull --ff-only origin main

echo "==> disco antes"
df -h /

if [ -n "${GHCR_TOKEN:-}" ]; then
    echo "==> ghcr login"
    echo "$GHCR_TOKEN" | docker login ghcr.io -u "${GHCR_USER:?}" --password-stdin
    # Token do job expira com ele; não deixar credencial no ~/.docker.
    trap 'docker logout ghcr.io >/dev/null 2>&1 || true' EXIT
fi

echo "==> pull images ($IMAGE_TAG)"
$COMPOSE pull api frontend

echo "==> migrate"
$COMPOSE run --rm api alembic upgrade head

echo "==> up"
$COMPOSE up -d

# Depois do `up`, as imagens em uso estão protegidas; o resto (versões
# anteriores, build cache herdado de quando o build era aqui) sai. Nunca
# `--volumes`: frontend_build e caddy_data são volumes nomeados.
echo "==> liberar disco"
docker image prune -af || echo "aviso: image prune falhou, seguindo"
docker builder prune -af || echo "aviso: builder prune falhou, seguindo"

echo "==> disco final"
df -h /

echo "==> done"
