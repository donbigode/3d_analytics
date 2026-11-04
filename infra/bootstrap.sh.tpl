#!/usr/bin/env bash
# Bootstrap idempotente do 3D Analytics em Lightsail Ubuntu 22.04.
# Renderizado pelo Terraform via templatefile() em lightsail.tf.
# Roda como root no primeiro boot (Lightsail wrappa em #!/bin/sh).
set -euo pipefail

DUCKDNS_SUBDOMAIN="${duckdns_subdomain}"
DUCKDNS_TOKEN="${duckdns_token}"
REPO_URL="${github_repo_url}"
DEPLOY_PUB_KEY="${deploy_ssh_pub_key}"
STATIC_IP="${static_ip}"

ENV_FILE=/etc/3d-analytics/.env
REPO_DIR=/opt/3d-analytics

trap 'echo "BOOTSTRAP FALHOU na linha $LINENO (exit $?)" >&2' ERR

# Usuário deploy PRIMEIRO, antes de qualquer coisa que dependa de rede/apt.
# Na 1ª tentativa da nano (2026-11-03) o script morreu antes deste passo, e
# sem ele não havia como entrar pra ler o log (a chave de admin tem
# passphrase). Grupo `adm` = lê /var/log/cloud-init-output.log.
echo "==> deploy user"
if ! id deploy >/dev/null 2>&1; then
    useradd -m -s /bin/bash -G adm deploy
fi
mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
echo "$DEPLOY_PUB_KEY" > /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

# Swap antes do apt/docker: no nano (512 MB) a instalação roda apertada.
echo "==> swap 2GB"
if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# No primeiro boot o unattended-upgrades costuma estar segurando o lock do
# dpkg; esperar em vez de falhar na hora.
APT="apt-get -o DPkg::Lock::Timeout=900"

echo "==> updating apt"
$APT update -qq

echo "==> base packages"
DEBIAN_FRONTEND=noninteractive $APT install -y -qq \
    git curl openssl ufw ca-certificates gnupg

echo "==> docker via get.docker.com"
if ! command -v docker >/dev/null 2>&1; then
    # O script do get.docker.com chama apt-get sem timeout de lock.
    for attempt in 1 2 3 4 5; do
        while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do sleep 5; done
        curl -fsSL https://get.docker.com | sh && break
        echo "get.docker.com falhou (tentativa $attempt); aguardando"
        sleep 60
    done
    command -v docker >/dev/null 2>&1
fi
usermod -aG docker deploy

echo "==> directories"
mkdir -p /etc/3d-analytics /var/lib/3d-analytics/db /var/lib/3d-analytics/storage

echo "==> repo clone"
if [ ! -d "$REPO_DIR/.git" ]; then
    git clone "$REPO_URL" "$REPO_DIR"
else
    git -C "$REPO_DIR" pull --ff-only origin main || true
fi
chown -R deploy:deploy "$REPO_DIR"

echo "==> .env (only if missing)"
if [ ! -f "$ENV_FILE" ]; then
    SESSION_SECRET=$(openssl rand -hex 32)
    POSTGRES_PASSWORD=$(openssl rand -hex 24)
    cat > "$ENV_FILE" <<EOF
SESSION_SECRET=$SESSION_SECRET
POSTGRES_USER=app_prod
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=app_prod
DATABASE_URL=postgresql+asyncpg://app_prod:$POSTGRES_PASSWORD@db:5432/app_prod
BIND_HOST=$DUCKDNS_SUBDOMAIN.duckdns.org
CORS_ORIGINS=https://$DUCKDNS_SUBDOMAIN.duckdns.org
STORAGE_DIR=/data/storage
ENV=prod
SEED_USER_OTAVIO_EMAIL=otaviorgeraldo@gmail.com
SEED_USER_ANA_EMAIL=anarqborges@gmail.com
SEED_INITIAL_PASSWORD=F1odor_213
EOF
    chmod 600 "$ENV_FILE"
    chown deploy:deploy "$ENV_FILE"
fi

echo "==> symlink .env into repo dir (Compose interpolation cwd)"
ln -sf "$ENV_FILE" "$REPO_DIR/.env"

# Sempre com o IP estático explícito: `ip=` vazio faria o DuckDNS usar o IP de
# origem, e uma instância nova (ainda sem o IP estático) roubaria o domínio.
echo "==> DuckDNS update"
curl -s "https://www.duckdns.org/update?domains=$DUCKDNS_SUBDOMAIN&token=$DUCKDNS_TOKEN&ip=$STATIC_IP" || true

# Imagens vêm prontas do GHCR (deploy.yml). Build local só como plano B, se o
# pacote estiver privado — e num nano de 512 MB ele é lento.
echo "==> docker compose pull"
cd "$REPO_DIR"
docker compose -f docker-compose.prod.yml pull api frontend \
  || docker compose -f docker-compose.prod.yml build api frontend

echo "==> db first + migrate + seed"
docker compose -f docker-compose.prod.yml up -d db
sleep 12
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml run --rm api python -m backend.scripts.seed_users

echo "==> up all"
docker compose -f docker-compose.prod.yml up -d

echo "==> duckdns cron"
( crontab -l 2>/dev/null | grep -v duckdns; \
  echo "0 */6 * * * curl -s 'https://www.duckdns.org/update?domains=$DUCKDNS_SUBDOMAIN&token=$DUCKDNS_TOKEN&ip=$STATIC_IP'" \
) | crontab -

echo "==> done"
docker compose -f docker-compose.prod.yml ps
