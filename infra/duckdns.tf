data "http" "duckdns_update" {
  url = "https://www.duckdns.org/update?domains=${var.duckdns_subdomain}&token=${var.duckdns_token}&ip=${aws_lightsail_static_ip.app.ip_address}"

  request_headers = {
    Accept = "text/plain"
  }

  depends_on = [aws_lightsail_static_ip_attachment.app]
}

# Sanity check — se DuckDNS devolveu "KO", a gente para o apply ali.
output "duckdns_response" {
  value = data.http.duckdns_update.response_body
  precondition {
    condition     = data.http.duckdns_update.status_code == 200
    error_message = "DuckDNS HTTP ${data.http.duckdns_update.status_code}"
  }
}
