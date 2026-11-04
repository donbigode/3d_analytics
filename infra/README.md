# Infra — 3D Analytics

Terraform pra subir o MVP em AWS Lightsail us-east-1.

## Pré-requisitos

- [Terraform 1.5+](https://developer.hashicorp.com/terraform/install)
- [AWS CLI configurado](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html) com credenciais que possam criar Lightsail (geralmente a chave de admin da sua conta).
- Conta DuckDNS criada com subdomínio reservado.
- Usuário IAM com `lightsail:*` (policy inline serve). Produção roda num `nano_3_0` ($5/mês, 512 MB RAM, 20 GB SSD + 2 GB de swap); alternativas: `micro_3_0` ($7, 1 GB) ou `small_3_0` ($12, 2 GB). **Não troque `bundle_id` de uma instância existente**: força replace, e o replace apaga o disco com o Postgres — pra mudar de plano, veja [Trocar de instância](#trocar-de-instância).
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

## Trocar de instância

Mudar de plano (ou recriar a máquina) sem perder dados: subir uma instância nova ao lado, copiar o estado com `migrate-data.sh` e mover o IP estático. Como o IP não muda, DuckDNS, o secret `LIGHTSAIL_IP` e o `SERVICE_URL` do listener ficam iguais.

Foi assim a migração micro → nano de 2026-11-04 (PRs #38, #39 e o que removeu a micro): ~2 min de site fora do ar, contagem de linhas conferida nas 29 tabelas.

Roteiro:

1. Em `lightsail.tf`, adicionar um segundo `aws_lightsail_instance` (+ `aws_lightsail_instance_public_ports`) com o plano novo e `terraform apply`. O bootstrap leva ~5 min; dá pra acompanhar com `ssh -i deploy_key deploy@<ip_dinamico> 'grep "==>" /var/log/cloud-init-output.log'` — o user `deploy` é o primeiro passo do bootstrap.
2. `./migrate-data.sh <ip_estatico> <ip_dinamico_da_nova>` — para a API da antiga (o downtime começa aqui), copia banco, storage, `.env` e `caddy_data`, e confere `count(*)` por tabela. O health check do fim pode falhar se a API ainda estiver subindo; confira de novo com `wget` no `api:8000/healthz`.
3. Apontar `aws_lightsail_static_ip_attachment.app` pra instância nova e `terraform apply`.
4. Com tudo estável, remover a instância antiga do `.tf` e `terraform apply`. Só então ela deixa de cobrar.

Rollback antes do passo 4: apontar o attachment de volta pra antiga e `docker compose -f docker-compose.prod.yml start api` nela.

O bootstrap é POSIX `sh`: o Lightsail roda o user_data com o dash do Ubuntu 22.04, que não tem `pipefail`. Bashismo ali mata o script na primeira linha, sem log útil.

## Destroy

```bash
terraform destroy
```

Apaga: instância, IP estático, key pairs, regras de firewall. **Não** apaga o subdomínio DuckDNS (faça pelo painel deles).

## Backup

Nenhum — esse MVP roda sem snapshot por escolha. Se a instância morrer, `terraform destroy && terraform apply` reconstrói; os dados (orçamentos, materiais) **não voltam**. Refaça via UI.
