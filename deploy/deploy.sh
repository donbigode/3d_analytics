#!/usr/bin/env bash
# deploy/deploy.sh — usado pelo GitHub Actions e disponível pra rodar
# manualmente via SSH no servidor. Idempotente.
set -euo pipefail

cd /opt/3d-analytics

echo "==> git pull"
git pull --ff-only origin main

# O build monta uma imagem nova de vários GB enquanto a antiga ainda está em
# uso, e o `docker image prune` que existia só no fim do script nunca tocava no
# build cache — que é justamente o que mais cresce, por causa dos
# `--mount=type=cache` do pip. Resultado: o deploy morria com "no space left on
# device" no meio do `exporting to image`, como em 2026-09-25.
#
# Liberar ANTES de construir. `image prune -a` não remove imagem em uso por
# container rodando, então a versão no ar está protegida; se os containers
# estiverem parados por um deploy anterior que falhou, o pior caso é reconstruir
# ou repuxar, nunca perder dado.
#
# Nunca `--volumes` aqui: frontend_build e caddy_data são volumes nomeados, e o
# script não deve depender de nós lembrarmos que o Postgres está num bind-mount.
echo "==> disco antes"
df -h /

echo "==> liberar disco (build cache limitado a 4GB, imagens órfãs removidas)"
docker builder prune -f --max-used-space 4GB \
  || docker builder prune -f --keep-storage 4GB \
  || docker builder prune -f \
  || echo "aviso: builder prune falhou, seguindo"
docker image prune -af || echo "aviso: image prune falhou, seguindo"

echo "==> disco depois"
df -h /

echo "==> build images"
docker compose -f docker-compose.prod.yml build api frontend

echo "==> migrate"
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

echo "==> up"
docker compose -f docker-compose.prod.yml up -d

echo "==> prune dangling images"
docker image prune -f

echo "==> disco final"
df -h /

echo "==> done"
