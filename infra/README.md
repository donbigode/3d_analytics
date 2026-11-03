# Infra — 3D Analytics

Terraform pra subir o MVP em AWS Lightsail us-east-1.

## Pré-requisitos

- [Terraform 1.5+](https://developer.hashicorp.com/terraform/install)
- [AWS CLI configurado](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html) com credenciais que possam criar Lightsail (geralmente a chave de admin da sua conta).
- Conta DuckDNS criada com subdomínio reservado.
- Usuário IAM com `lightsail:*` (policy inline serve). Bundles: `nano_3_0` ($5/mês, 512 MB RAM, 20 GB SSD — destino atual, ver [Migração micro → nano](#migração-micro--nano)), `micro_3_0` ($7/mês, 1 GB RAM, 40 GB SSD — a instância `app` original) ou `small_3_0` ($12/mês, 2 GB RAM, 60 GB SSD). **Não troque `bundle_id` de uma instância existente**: força replace, e o replace apaga o disco com o Postgres.
- Par de chaves SSH pro user `deploy` do GH Actions:
  ```bash
  ssh-keygen -t ed25519 -f ./deploy_key -N ''
  ```

## Bootstrap

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Edite terraform.tfvars com seus valores.

terraform init
terraform plan      # confirme o que vai ser criado
terraform apply
```

Output esperado:
```
public_ip = "3.x.x.x"
dns_name  = "3d-borges.duckdns.org"
ssh_command_admin  = "ssh ubuntu@3.x.x.x"
ssh_command_deploy = "ssh deploy@3.x.x.x"
```

## Configure GitHub Secrets

```bash
gh secret set LIGHTSAIL_IP --body "$(terraform output -raw public_ip)"
gh secret set DEPLOY_SSH_KEY < ./deploy_key
```

## Primeira validação

```bash
ssh ubuntu@$(terraform output -raw public_ip) \
  'sudo tail -50 /var/log/cloud-init-output.log'
```

Cloud-init demora ~5 min na primeira vez. Quando terminar, abra:
```
https://3d-borges.duckdns.org
```

Login com:
- `otaviorgeraldo@gmail.com` / `F1odor_213`
- `anarqborges@gmail.com`    / `F1odor_213`

A UI vai forçar troca de senha imediata.

## Migração micro → nano

Produção só-CRUD (sem o extra `[ai]`, imagens prontas do GHCR) cabe no `nano_3_0`: ~150 MB de RAM nos containers, medido em 2026-11-02. Economia: $7 → $5/mês. O IP estático muda de instância, então DuckDNS, o secret `LIGHTSAIL_IP` e o `SERVICE_URL` do listener não mudam.

Pré-requisito: o deploy via GHCR já rodou ao menos uma vez (há imagem `latest` no `ghcr.io/donbigode/3d_analytics-api`). Se o pacote estiver privado, o bootstrap da nano cai no build local, que é lento em 512 MB — deixe os pacotes públicos (o repo já é) ou espere.

```bash
cd infra

# 1. Cria a nano ao lado da micro (nada muda na micro). ~5 min de cloud-init.
terraform apply -var nano_enabled=true
NANO=$(terraform output -raw nano_public_ip)     # IP dinâmico, só pra migrar
OLD=$(terraform output -raw public_ip)           # IP estático, ainda na micro
ssh -i deploy_key deploy@$NANO 'cloud-init status --wait'

# 2. Copia banco, storage, .env e certificado. Para a API da micro (downtime
#    começa aqui) e confere contagem de linhas tabela a tabela.
./migrate-data.sh $OLD $NANO

# 3. Move o IP estático pra nano. Domínio volta a responder.
terraform apply -var nano_enabled=true -var active_instance=nano
curl -fsS https://zoryx3d.duckdns.org/api/healthz
```

Rollback (enquanto a micro existir): `terraform apply -var nano_enabled=true -var active_instance=micro` e `ssh -i deploy_key deploy@$OLD 'cd /opt/3d-analytics && docker compose -f docker-compose.prod.yml start api'`.

Depois de alguns dias estável: remover `aws_lightsail_instance.app` e `aws_lightsail_instance_public_ports.app` do `lightsail.tf`, apontar o `aws_lightsail_static_ip_attachment.app` direto pra `aws_lightsail_instance.nano[0].name` (a ternária referencia a `app`), fixar `nano_enabled = true` no `terraform.tfvars` e `terraform apply` — é aí que a micro deixa de cobrar.

## Destroy

```bash
terraform destroy
```

Apaga: instância, IP estático, key pairs, regras de firewall. **Não** apaga o subdomínio DuckDNS (faça pelo painel deles).

## Backup

Nenhum — esse MVP roda sem snapshot por escolha. Se a instância morrer, `terraform destroy && terraform apply` reconstrói; os dados (orçamentos, materiais) **não voltam**. Refaça via UI.
