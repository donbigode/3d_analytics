resource "aws_lightsail_key_pair" "admin" {
  name       = "${var.instance_name}-admin"
  public_key = var.ssh_pub_key
}

locals {
  bootstrap_vars = {
    deploy_ssh_pub_key = var.deploy_ssh_pub_key
    duckdns_subdomain  = var.duckdns_subdomain
    duckdns_token      = var.duckdns_token
    github_repo_url    = var.github_repo_url
    # O IP estático é quem atende o domínio. O bootstrap e o cron do DuckDNS
    # mandam ele explícito: com `ip=` vazio o DuckDNS usa o IP de origem da
    # requisição, e uma instância nova (ainda sem o IP estático) roubaria o
    # domínio da que está no ar.
    static_ip = aws_lightsail_static_ip.app.ip_address
  }

  public_ports = [
    { port = 22, cidrs = [var.allowed_ssh_cidr] },
    { port = 80, cidrs = ["0.0.0.0/0"] },
    { port = 443, cidrs = ["0.0.0.0/0"] },
  ]
}

# Instância única de produção: nano_3_0 desde 2026-11-04. Substituiu a micro
# original (`aws_lightsail_instance.app`, micro_3_0), removida após a
# migração — ver "Trocar de instância" no README. O nome do recurso ficou
# `nano` pra não precisar mexer no state.
resource "aws_lightsail_instance" "nano" {
  name              = "${var.instance_name}-nano"
  availability_zone = var.availability_zone
  blueprint_id      = "ubuntu_22_04"
  bundle_id         = var.bundle_id
  key_pair_name     = aws_lightsail_key_pair.admin.name

  user_data = templatefile("${path.module}/bootstrap.sh.tpl", local.bootstrap_vars)

  lifecycle {
    # user_data only fires on first boot; mudanças posteriores não tem efeito
    # mesmo se aplicarmos. Ignorar evita prompts de "replace" no plan.
    ignore_changes = [user_data]
  }
}

moved {
  from = aws_lightsail_instance.nano[0]
  to   = aws_lightsail_instance.nano
}

resource "aws_lightsail_static_ip" "app" {
  name = "${var.instance_name}-ip"
}

resource "aws_lightsail_static_ip_attachment" "app" {
  static_ip_name = aws_lightsail_static_ip.app.name
  instance_name  = aws_lightsail_instance.nano.name
}

resource "aws_lightsail_instance_public_ports" "nano" {
  instance_name = aws_lightsail_instance.nano.name

  dynamic "port_info" {
    for_each = local.public_ports
    content {
      protocol  = "tcp"
      from_port = port_info.value.port
      to_port   = port_info.value.port
      cidrs     = port_info.value.cidrs
    }
  }
}

moved {
  from = aws_lightsail_instance_public_ports.nano[0]
  to   = aws_lightsail_instance_public_ports.nano
}
