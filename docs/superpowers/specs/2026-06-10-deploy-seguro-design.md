# Deploy Seguro do 3D Analytics — Design

**Data:** 2026-06-10
**Autor:** Otavio Geraldo (com Claude Opus 4.7)
**Status:** Aprovado pra implementação

## Resumo

Subir o MVP do 3D Analytics em produção como serviço interno (uso só de
Otavio + Ana Clara — clientes interagem via Shopee). Infra como código
em Terraform, hospedagem AWS Lightsail $7/mês em us-east-1, HTTPS via
Caddy + Let's Encrypt em subdomínio DuckDNS gratuito, deploy contínuo
via GitHub Actions ao fazer push na branch `main`.

Sem backup automatizado — se algo quebrar, refaz `terraform apply` e
re-popula os dados manualmente. Aceitável pelo perfil "MVP interno".

## Goals e Não-goals

**Goals:**

- Servidor único acessível por HTTPS com certificado válido.
- Dois usuários iniciais provisionados (Otavio + Ana Clara) com senha
  temporária `F1odor_213` que **deve** ser trocada no primeiro login.
- Secrets infra (SESSION_SECRET, POSTGRES_PASSWORD) gerados
  aleatoriamente no provisionamento; nunca commitados.
- `terraform apply` + `git push origin main` é tudo que precisa pra
  ter o serviço no ar.
- Postgres não exposto na internet; só 22/80/443 abertos.

**Não-goals:**

- Alta disponibilidade (single instance, single AZ).
- Backup automático (usuário aceita risco — refaz se quebrar).
- Multi-tenant (só 2 usuários internos).
- Logo do site público / portal do cliente (Shopee cobre isso).
- Migrar pra ECS/RDS/Fargate (modular, dá pra fazer depois).

## Arquitetura

### Topologia de rede

```
   Internet
      │
      ▼
   DuckDNS  ────►  3d-borges.duckdns.org → 3.x.x.x (Lightsail static IP)
      │
      ▼
┌─ Lightsail Instance (Ubuntu 22.04, nano_3_0 / $7) ───────────┐
│                                                               │
│  Lightsail Firewall: 22 (SSH, restrito ao IP do dono) ·       │
│                       80 (HTTP → ACME challenge) · 443 (HTTPS)│
│                                                               │
│  ┌─ docker-compose.prod.yml ───────────────────────────┐      │
│  │  caddy  :80 :443   auto-TLS + reverse proxy         │      │
│  │    ├─ /api/*  →  api:8000                           │      │
│  │    └─ /*      →  frontend (static)                  │      │
│  │  api    :8000      FastAPI + alembic + watcher      │      │
│  │  db     :5432      Postgres (sem porta exposta)     │      │
│  │  frontend          SvelteKit static-adapter         │      │
│  └─────────────────────────────────────────────────────┘      │
│                                                               │
│  Volumes:                                                     │
│    /var/lib/3d-analytics/db        → postgres data           │
│    /var/lib/3d-analytics/storage   → uploads, library assets │
└───────────────────────────────────────────────────────────────┘
```

### Estrutura do repositório

```
infra/                            ← NOVO
├── main.tf                       Provider + terraform block
├── variables.tf                  ssh_pub_key, duckdns_token, duckdns_subdomain, allowed_ssh_cidr
├── terraform.tfvars.example      Template documentado (commitado)
├── terraform.tfvars              Valores reais (gitignored)
├── lightsail.tf                  Instance + static IP + firewall
├── duckdns.tf                    http_request pra updar o subdomínio
├── outputs.tf                    public_ip, dns_name, ssh_command
├── cloud-init.yaml               First-boot: Docker, user deploy, .env, primeiro up
├── .gitignore                    *.tfstate, *.tfvars, .terraform/
└── README.md                     Comandos pra bootstrap inicial

docker-compose.prod.yml           ← NOVO (separado do dev)
deploy/
├── Caddyfile                     ← NOVO (config do reverse proxy)
└── deploy.sh                     ← NOVO (script SSH-friendly, idempotente)

backend/scripts/
└── seed_users.py                 ← NOVO (provisiona 2 usuários iniciais)

migrations/versions/
└── 0021_must_change_password.py  ← NOVO

.github/workflows/
└── deploy.yml                    ← NOVO
```

## Componentes

### 1. Módulo Terraform (`infra/`)

**Recursos AWS criados:**

- `aws_lightsail_instance` — `bundle_id = "nano_3_0"` ($7), `blueprint_id = "ubuntu_22_04"`, `user_data` aponta pro `cloud-init.yaml`.
- `aws_lightsail_static_ip` + `aws_lightsail_static_ip_attachment` — IP fixo que sobrevive reinicialização da instância.
- `aws_lightsail_instance_public_ports`:
  - `22/tcp` aberto **só** pra `var.allowed_ssh_cidr` (default `0.0.0.0/0` mas Otavio coloca seu IP residencial pra apertar).
  - `80/tcp` aberto pra `0.0.0.0/0` (necessário pro ACME-HTTP-01 do Let's Encrypt).
  - `443/tcp` aberto pra `0.0.0.0/0`.
- `aws_lightsail_key_pair` — gera par de chaves SSH; chave privada nunca toca o repo (Terraform sensitive output).

**Provider DuckDNS** via `http` data source: faz `GET https://www.duckdns.org/update?domains=<sub>&token=<token>&ip=<lightsail_ip>` no apply. Mesma chamada vai num cron `* */6 * * *` no servidor (defensa contra mudança de IP — embora o static IP da Lightsail não mude).

**Output:**
- `public_ip` (string)
- `dns_name` = `${var.duckdns_subdomain}.duckdns.org`
- `ssh_command` = `ssh -i ./id_ed25519 ubuntu@<ip>`

**State:** `terraform.tfstate` fica no `.gitignore`; usuário guarda local. Documentado no `README.md` que é responsabilidade dele não perder.

### 2. cloud-init.yaml — primeiro boot

Roda como root no primeiro boot. Tarefas, em ordem:

1. `apt update && apt install -y docker.io docker-compose-plugin git ufw curl`
2. Cria user `deploy`, adiciona ao grupo `docker`.
3. Recebe via `write_files` a chave pública do GitHub Actions em `~deploy/.ssh/authorized_keys`.
4. `git clone https://github.com/<owner>/3d-analytics.git /opt/3d-analytics`.

   **Pressuposto:** o repo está no GitHub e é **público OU** acessível com a chave deploy. Pra MVP recomendamos público — não tem nenhum segredo no código (todos os secrets ficam em variáveis de ambiente ou no Settings DB). Se preferir privado, o cloud-init recebe a `DEPLOY_SSH_KEY` privada e o `git clone` usa `git@github.com:...` em vez de HTTPS.

   **Pré-requisito do deploy:** o repo precisa estar publicado no GitHub antes do `terraform apply`. Implementação plan adiciona um passo "criar repo + push inicial" antes do Terraform.
5. Cria `/etc/3d-analytics/.env`, chmod 600, owner `deploy:deploy`. Variáveis (`BIND_HOST` é injetado pelo Terraform via template):
   - `SESSION_SECRET=$(openssl rand -hex 32)`
   - `POSTGRES_USER=app_prod`
   - `POSTGRES_PASSWORD=$(openssl rand -hex 24)`
   - `POSTGRES_DB=app_prod`
   - `DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}`
   - `BIND_HOST=3d-borges.duckdns.org`  (vem do `var.duckdns_subdomain` do TF)
   - `CORS_ORIGINS=https://${BIND_HOST}`
   - `STORAGE_DIR=/data/storage`
   - `ENV=prod` (sinaliza pro app usar cookies `secure=True`)
6. `mkdir -p /var/lib/3d-analytics/db /var/lib/3d-analytics/storage`
7. `docker compose -f /opt/3d-analytics/docker-compose.prod.yml up -d`
8. Aguarda DB ficar saudável, então roda `alembic upgrade head` + `python -m backend.scripts.seed_users`.
9. `(crontab -l 2>/dev/null; echo '0 */6 * * * curl -s https://www.duckdns.org/update?...') | crontab -`

### 3. docker-compose.prod.yml

Difere do `docker-compose.yml` (dev) em:

- **Sem bind-mount do código** — só imagens construídas pelo `Dockerfile`.
- **Sem `WATCHFILES_FORCE_POLLING`** — código é imutável em prod.
- **`db.ports` removido** — não expõe 5432 publicamente.
- **Adiciona `caddy`** com `image: caddy:2-alpine`, volumes pro Caddyfile + storage de certificados.
- **Volumes nomeados de host** apontando pra `/var/lib/3d-analytics/` (sobrevive a recriação dos containers).
- **`restart: unless-stopped`** em todos os serviços.
- **`env_file: /etc/3d-analytics/.env`** (não os defaults inseguros).

### 4. Caddyfile

```caddyfile
{
  email otaviorgeraldo@gmail.com
}

{$BIND_HOST} {
  encode gzip
  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains"
    X-Content-Type-Options "nosniff"
    X-Frame-Options "DENY"
    Referrer-Policy "strict-origin-when-cross-origin"
  }
  handle_path /api/* {
    reverse_proxy api:8000
  }
  handle {
    root * /srv/frontend
    try_files {path} /index.html
    file_server
  }
  rate_limit {
    zone login {
      key {remote_host}
      events 60
      window 1m
    }
    match path /api/auth/login
  }
}
```

**Decisão:** Caddy oficial não tem rate limit nativo e o build customizado adiciona ~5 min de tempo de build na imagem. Pra simplificar, fazemos rate limit no FastAPI lado server via middleware `slowapi` (já popular no ecossistema). Limites:

- `/api/auth/login`: 10 req/min/IP
- Resto: 120 req/min/IP

Trade-off explícito: rate-limit no app significa que requests bobas chegam até o Python (gasta CPU), mas com 2 usuários internos isso é trivial.

### 5. Mudanças no app

**Migration `0021_must_change_password`:**
```python
op.add_column(
    "users",
    sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
)
```

**Schema/route changes:**
- `UserOut.must_change_password: bool` — adicionar campo.
- `GET /auth/me` retorna o flag.
- **Novo endpoint** `POST /auth/change-password` (não existe hoje, confirmado): aceita `{current_password, new_password}`, valida o atual, hashea o novo com Argon2id, **limpa** `must_change_password`. Erro 401 se current_password errada; erro 400 se new_password < 12 chars.
- Frontend: após login, se `must_change_password === true`, abre modal forçando troca de senha — bloqueia navegação até trocar.

**Cookies em prod:**
- `secure=True` (só HTTPS)
- `samesite="strict"`
- Ativados quando `ENV=prod` no Settings (nova flag de configuração).

**`backend/scripts/seed_users.py`:**
- Idempotente: se email já existe, pula.
- Lê os 2 emails de variáveis ambiente `SEED_USER_OTAVIO_EMAIL`, `SEED_USER_ANA_EMAIL`, e senha `SEED_INITIAL_PASSWORD`.
- Argon2id já está em uso (`pwd_argon2_*` no Settings).
- Marca `must_change_password=True`.

### 6. GitHub Actions — `.github/workflows/deploy.yml`

Trigger: `push` em `main`.

Steps:
1. `actions/checkout@v4`
2. `appleboy/ssh-action@v1` — SSH no servidor como `deploy`, roda:
   ```bash
   cd /opt/3d-analytics
   git pull origin main
   docker compose -f docker-compose.prod.yml build api frontend
   docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
   docker compose -f docker-compose.prod.yml up -d
   docker image prune -f
   ```

Downtime esperado: ~30s (tempo do `up -d` recriar os containers). Aceitável pra serviço interno.

Secrets GH (configurados via `gh secret set`):
- `LIGHTSAIL_IP`
- `DEPLOY_SSH_KEY`

## Fluxo de Dados (deploy inicial)

```
1. Otavio: cd infra && cp terraform.tfvars.example terraform.tfvars
   (preenche duckdns_token, ssh_pub_key, allowed_ssh_cidr)

2. Otavio: terraform init && terraform apply
   ├─ Cria Lightsail instance + static IP
   ├─ Aplica firewall rules
   ├─ Updates DuckDNS apontando pro IP
   └─ Outputs: public_ip, dns_name

3. cloud-init roda no servidor:
   ├─ Instala Docker
   ├─ Cria user deploy + chave SSH
   ├─ Clona o repo
   ├─ Gera .env com secrets aleatórios
   ├─ Sobe stack via docker-compose.prod.yml
   ├─ Aguarda DB healthy
   ├─ Roda migrations + seed_users
   └─ Configura cron DuckDNS

4. Otavio configura GH Secrets:
   gh secret set LIGHTSAIL_IP --body "$(terraform output -raw public_ip)"
   gh secret set DEPLOY_SSH_KEY < deploy_id_ed25519

5. Otavio: git push origin main
   └─ GH Actions roda deploy (pull + build + migrate + up)

6. Otavio acessa https://3d-borges.duckdns.org
   ├─ Login com otaviorgeraldo@gmail.com / F1odor_213
   └─ Modal força troca de senha imediata.
   Mesmo pra Ana Clara depois.

7. Acessa /materials, /settings, etc. e configura
   (densities corretas, preço da impressora, etc. — fora do escopo desse spec).
```

## Tratamento de erros

**Falha no `terraform apply`:**
- Lightsail bundle inválido / região errada → mensagem clara do TF, sem recurso parcialmente criado (TF é transacional).
- `terraform destroy` desfaz tudo se precisar começar de novo.

**Falha no cloud-init (no boot da instância):**
- Logs em `/var/log/cloud-init-output.log` no servidor.
- README.md do `infra/` documenta `ssh ubuntu@<ip>` e `sudo cat /var/log/cloud-init-output.log`.
- Se falhou na geração de secrets, `sudo /opt/3d-analytics/deploy/bootstrap.sh` re-roda idempotentemente.

**Falha no GH Actions deploy:**
- Workflow falha → não muda estado em produção (ainda roda o último deploy bom).
- Se `alembic upgrade head` falhar, container `api` reinicia em loop com a versão velha — Caddy continua servindo 503. Otavio SSH no servidor e roda `alembic downgrade` se necessário.

**Falha de TLS (Let's Encrypt rate limit ou DNS errado):**
- Caddy loga e fica servindo HTTP no 80 enquanto retenta. Detectável pelo `journalctl -u docker`/`docker logs caddy`.
- Solução: confirmar DuckDNS atualizado, esperar 30 min e reiniciar Caddy.

**Brute force no login:**
- Caddy rate limit (60/min/IP) ou middleware FastAPI cobre.
- Argon2id já lento o suficiente pra desincentivar.

## Teste

Spec não exige testes automatizados novos — a infra valida-se manualmente:

1. `terraform plan` antes de cada apply (dry-run).
2. Smoke test pós-deploy:
   - `curl -sf https://3d-borges.duckdns.org/healthz` → 200
   - Login com Otavio → modal de troca de senha aparece
   - Login com Ana → modal de troca de senha aparece
   - SSH no servidor → `docker compose ps` → todos `healthy`
3. CI-side: workflow GH Actions falha rápido se SSH ou comandos derem erro.

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Lightsail $7 sem RAM pra WeasyPrint + Postgres + LLM búsca | média | médio | Swap de 2GB ativado no cloud-init |
| Subdomínio DuckDNS sumir / mudar política | baixa | alto | Migração simples pra DNS pago se acontecer (Cloudflare grátis também serve) |
| Estado Terraform perdido (laptop quebrado) | média | alto | README documenta `terraform import` pros recursos existentes; Otavio commitar criptografado num gist privado é opção (fora do MVP) |
| Senha temporária vazada antes da troca | baixa | médio | DuckDNS subdomain não é conhecido publicamente até o deploy; senha forte; HTTPS desde o primeiro acesso |
| Volume `/var/lib/3d-analytics` enchendo | média | médio | Cron mensal `docker system prune -af` + monitoramento manual via `df -h` |

## Custos mensais estimados

| Item | USD/mês | R$/mês (5,20) |
|---|---|---|
| Lightsail nano_3_0 | 7,00 | 36,40 |
| Static IP (incluso enquanto attachado) | 0 | 0 |
| Egress (1TB incluso, fácil suficiente pra 2 usuários internos) | 0 | 0 |
| DuckDNS subdomain | 0 | 0 |
| Let's Encrypt | 0 | 0 |
| GitHub Actions (2000 min free) | 0 | 0 |
| **Total** | **7,00** | **36,40** |

## Roadmap pós-MVP (fora desse spec)

Itens conscientemente adiados:

- Backup automatizado (Lightsail auto-snapshot ou pg_dump → S3)
- Migration pra ECS/Fargate + RDS quando virar produção real
- Monitoring (Sentry / CloudWatch)
- Logs estruturados centralizados
- Domínio próprio (.com.br) substituindo DuckDNS
- 2FA pros logins
- WAF / Cloudflare na frente
- IaC pros GH Actions secrets (não tem provider terraform-github bom pra isso sem expor token)
