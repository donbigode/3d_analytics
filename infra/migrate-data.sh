#!/usr/bin/env bash
# infra/migrate-data.sh — copia o estado de produção de uma instância pra outra.
# Roda do SEU laptop, como o user `deploy` (chave ./deploy_key), passando os
# dados pelo laptop. Feito pra migração micro → nano (ver README), mas não
# depende de bundle.
#
#   ./migrate-data.sh <host_origem> <host_destino>
#
# O que copia: dump do Postgres, /var/lib/3d-analytics/storage, o .env de
# produção (mesmo SESSION_SECRET = sessões continuam válidas; mesmos tokens de
# API) e o volume caddy_data (certificado TLS, evita reemitir).
#
# Downtime: a API da ORIGEM é parada no passo 1 pra não aceitar escrita depois
# do dump, e fica parada — é ela que o rollback religa. O domínio só volta a
# responder quando o IP estático for movido (terraform apply com
# active_instance = "nano").
set -euo pipefail

SRC="${1:?uso: $0 <host_origem> <host_destino>}"
DST="${2:?uso: $0 <host_origem> <host_destino>}"
KEY="$(dirname "$0")/deploy_key"
SSH_OPTS=(-i "$KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new)
COMPOSE="cd /opt/3d-analytics && docker compose -f docker-compose.prod.yml"
# Nome do volume = <projeto compose>_<volume>; o projeto é o nome do diretório.
CADDY_VOL="3d-analytics_caddy_data"

src() { ssh "${SSH_OPTS[@]}" "deploy@$SRC" "$@"; }
dst() { ssh "${SSH_OPTS[@]}" "deploy@$DST" "$@"; }

WORK="$(mktemp -d)"
chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT

counts() {
    # count(*) exato por tabela (n_live_tup é estimativa e atualiza com atraso).
    # SQL via stdin pra não brigar com três camadas de aspas.
    "$1" "$COMPOSE exec -T db sh -c 'psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -qAt'" <<'SQL'
select table_name,
       (xpath('/row/c/text()',
              query_to_xml(format('select count(*) as c from public.%I', table_name),
                           false, true, '')))[1]::text
from information_schema.tables
where table_schema = 'public' and table_type = 'BASE TABLE'
order by 1;
SQL
}

echo "==> [1/6] origem: parando a API (congela escrita)"
src "$COMPOSE stop api"

echo "==> [2/6] origem: exportando banco, storage, .env, caddy_data"
src "$COMPOSE exec -T db sh -c 'pg_dump -U \"\$POSTGRES_USER\" -Fc \"\$POSTGRES_DB\"'" > "$WORK/db.dump"
src "docker run --rm -v /var/lib/3d-analytics/storage:/s:ro alpine tar czf - -C /s ." > "$WORK/storage.tgz"
src "docker run --rm -v $CADDY_VOL:/d:ro alpine tar czf - -C /d ." > "$WORK/caddy_data.tgz"
src "cat /etc/3d-analytics/.env" > "$WORK/env"
counts src > "$WORK/counts.src"
ls -lh "$WORK"

echo "==> [3/6] destino: derrubando a stack do bootstrap e limpando banco/storage"
dst "$COMPOSE down"
# O Postgres do bootstrap foi inicializado com outra senha; o .env da origem só
# funciona num data dir novo, inicializado com ele.
dst "docker run --rm -v /var/lib/3d-analytics:/x alpine sh -c 'find /x/db /x/storage -mindepth 1 -delete'"

echo "==> [4/6] destino: .env da origem + storage + caddy_data"
dst "cat > /etc/3d-analytics/.env && chmod 600 /etc/3d-analytics/.env" < "$WORK/env"
dst "docker run --rm -i -v /var/lib/3d-analytics/storage:/s alpine tar xzf - -C /s" < "$WORK/storage.tgz"
dst "docker volume create $CADDY_VOL >/dev/null && docker run --rm -i -v $CADDY_VOL:/d alpine sh -c 'find /d -mindepth 1 -delete; tar xzf - -C /d'" < "$WORK/caddy_data.tgz"

echo "==> [5/6] destino: restaurando o banco"
dst "$COMPOSE up -d --wait db"
dst "$COMPOSE exec -T db sh -c 'pg_restore -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" --no-owner --exit-on-error'" < "$WORK/db.dump"
counts dst > "$WORK/counts.dst"
if ! diff -u "$WORK/counts.src" "$WORK/counts.dst"; then
    echo "ERRO: contagem de linhas diverge entre origem e destino (diff acima)." >&2
    echo "A API da origem segue parada; religue com: ssh deploy@$SRC '$COMPOSE start api'" >&2
    exit 1
fi
echo "contagens batem ($(wc -l < "$WORK/counts.src") tabelas)"

echo "==> [6/6] destino: migrations + stack completa"
dst "$COMPOSE run --rm api alembic upgrade head && $COMPOSE up -d"
dst "$COMPOSE exec -T caddy wget -qO- http://api:8000/healthz"
echo

cat <<EOF

==> dados migrados. Próximo passo: mover o IP estático.
    terraform apply -var nano_enabled=true -var active_instance=nano
Rollback (antes de destruir a origem):
    terraform apply -var nano_enabled=true -var active_instance=micro
    ssh deploy@<ip_estatico> '$COMPOSE start api'
EOF
