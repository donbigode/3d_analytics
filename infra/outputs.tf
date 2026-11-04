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
