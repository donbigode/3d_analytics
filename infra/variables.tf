variable "aws_region" {
  description = "Região AWS — us-east-1 é o mais barato."
  type        = string
  default     = "us-east-1"
}

variable "availability_zone" {
  description = "AZ específica dentro da região."
  type        = string
  default     = "us-east-1a"
}

variable "instance_name" {
  description = "Nome da instância no Lightsail."
  type        = string
  default     = "app-3d-analytics"
}

variable "bundle_id" {
  description = "Plano Lightsail. nano_3_0 = $5/mês, 512 MB RAM, 20 GB SSD (2GB swap criado no cloud-init). micro_3_0 = $7/mês, 1 GB. small_3_0 = $12/mês, 2 GB. ATENÇÃO: mudar numa instância existente força replace e apaga o disco com o Postgres; pra trocar de plano, migre (infra/migrate-data.sh)."
  type        = string
  default     = "nano_3_0"
}

variable "ssh_pub_key" {
  description = "Chave SSH pública (conteúdo do .pub) pra acesso administrativo."
  type        = string
}

variable "deploy_ssh_pub_key" {
  description = "Chave SSH pública do GitHub Actions deploy bot (autorizada no user 'deploy')."
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR autorizado a fazer SSH na porta 22. Default aberto — recomendado restringir ao seu IP."
  type        = string
  default     = "0.0.0.0/0"
}

variable "duckdns_subdomain" {
  description = "Subdomínio DuckDNS (sem o .duckdns.org). Ex: '3d-borges'."
  type        = string
}

variable "duckdns_token" {
  description = "Token da conta DuckDNS (visível em www.duckdns.org após login)."
  type        = string
  sensitive   = true
}

variable "github_repo_url" {
  description = "URL HTTPS pública do repo no GitHub (o cloud-init faz git clone disso)."
  type        = string
}

variable "aws_profile" {
  description = "Profile do ~/.aws/credentials a usar. Default null = usa o profile default ou env vars (AWS_PROFILE/AWS_ACCESS_KEY_ID)."
  type        = string
  default     = null
}
