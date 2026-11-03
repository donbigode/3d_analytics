output "public_ip" {
  value       = aws_lightsail_static_ip.app.ip_address
  description = "IP público fixo da instância. Use pra configurar o GH Actions secret LIGHTSAIL_IP."
}

output "dns_name" {
  value       = "${var.duckdns_subdomain}.duckdns.org"
  description = "FQDN público apontando pro IP via DuckDNS."
}

output "ssh_command_admin" {
  value       = "ssh ubuntu@${aws_lightsail_static_ip.app.ip_address}"
  description = "Comando pra SSH como root/admin (chave gerada local)."
}

output "ssh_command_deploy" {
  value       = "ssh deploy@${aws_lightsail_static_ip.app.ip_address}"
  description = "Comando pra SSH como user 'deploy' (chave do GitHub Actions)."
}

output "nano_public_ip" {
  value       = var.nano_enabled ? aws_lightsail_instance.nano[0].public_ip_address : null
  description = "IP público atual da instância nano. Antes do cutover é um IP dinâmico (use pra migrar os dados); depois do cutover vira o IP estático."
}
