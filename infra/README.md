# Infra — 3D Analytics

Terraform pra subir o MVP em AWS Lightsail us-east-1.

## Pré-requisitos

- [Terraform 1.5+](https://developer.hashicorp.com/terraform/install)
- [AWS CLI configurado](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html) com credenciais que possam criar Lightsail (geralmente a chave de admin da sua conta).
- Conta DuckDNS criada com subdomínio reservado.
- Usuário IAM com `lightsail:*` (policy inline serve). Os bundles atuais são `micro_3_0` ($7/mês, 1 GB RAM, 40 GB SSD — default) ou `small_3_0` ($12/mês, 2 GB RAM, 60 GB SSD). Pra trocar, edite `bundle_id` em `terraform.tfvars`.
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

## Destroy

```bash
terraform destroy
```

Apaga: instância, IP estático, key pairs, regras de firewall. **Não** apaga o subdomínio DuckDNS (faça pelo painel deles).

## Backup

Nenhum — esse MVP roda sem snapshot por escolha. Se a instância morrer, `terraform destroy && terraform apply` reconstrói; os dados (orçamentos, materiais) **não voltam**. Refaça via UI.
