resource "aws_lightsail_key_pair" "admin" {
  name       = "${var.instance_name}-admin"
  public_key = var.ssh_pub_key
}

resource "aws_lightsail_instance" "app" {
  name              = var.instance_name
  availability_zone = var.availability_zone
  blueprint_id      = "ubuntu_22_04"
  bundle_id         = var.bundle_id
  key_pair_name     = aws_lightsail_key_pair.admin.name

  user_data = templatefile("${path.module}/bootstrap.sh.tpl", {
    deploy_ssh_pub_key = var.deploy_ssh_pub_key
    duckdns_subdomain  = var.duckdns_subdomain
    duckdns_token      = var.duckdns_token
    github_repo_url    = var.github_repo_url
  })

  lifecycle {
    # user_data only fires on first boot; mudanças posteriores não tem efeito
    # mesmo se aplicarmos. Ignorar evita prompts de "replace" no plan.
    ignore_changes = [user_data]
  }
}

resource "aws_lightsail_static_ip" "app" {
  name = "${var.instance_name}-ip"
}

resource "aws_lightsail_static_ip_attachment" "app" {
  static_ip_name = aws_lightsail_static_ip.app.name
  instance_name  = aws_lightsail_instance.app.name
}

resource "aws_lightsail_instance_public_ports" "app" {
  instance_name = aws_lightsail_instance.app.name

  port_info {
    protocol  = "tcp"
    from_port = 22
    to_port   = 22
    cidrs     = [var.allowed_ssh_cidr]
  }
  port_info {
    protocol  = "tcp"
    from_port = 80
    to_port   = 80
    cidrs     = ["0.0.0.0/0"]
  }
  port_info {
    protocol  = "tcp"
    from_port = 443
    to_port   = 443
    cidrs     = ["0.0.0.0/0"]
  }
}
