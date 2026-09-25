from backend.infra.pdf.render import _env, render_quote_pdf


def _base_data(quote: dict) -> dict:
    return {
        "business_name": "Test", "business_tagline": None, "logo_url": None,
        "brand_color": "#111827", "currency": "BRL",
        "quote": quote,
        "items": [{"name": "Peca A", "filament_m": 5.0, "time_s": 1800, "qty": 1, "subtotal": 25.0}],
        "services": [{"name": "Slicing", "qty": 5, "rate": 1.0, "subtotal": 5.0}],
        "totals": {"cost": 30.0, "markup_pct": 50, "min_charge": 0, "total": 45.0},
    }


def test_render_pdf_basic():
    # seq presente — é o que a rota /quotes/{id}/pdf realmente passa hoje
    # (backend/api/routes/quotes/pdf.py inclui quote.seq no contexto desde
    # a #0042 rollout).
    data = _base_data({"id": "abc", "seq": 42, "kind": "commercial", "status": "orcado", "client": "Ana"})
    pdf = render_quote_pdf(data)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")

    # O número humano (#0042) precisa aparecer no HTML por trás do PDF —
    # não dá pra inspecionar texto dentro do PDF binário sem uma lib extra,
    # então valida direto o template que o WeasyPrint consome.
    html = _env.get_template("quote.html").render(**data)
    assert "#0042" in html


def test_render_pdf_without_seq_does_not_crash():
    # Regressão: um dict de quote sem "seq" (contexto antigo, ou um chamador
    # futuro que esqueça o campo) não pode derrubar a geração do PDF — é
    # muito pior não emitir o documento do que emiti-lo sem o número.
    data = _base_data({"id": "abc", "kind": "commercial", "status": "orcado", "client": "Ana"})
    pdf = render_quote_pdf(data)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")

    html = _env.get_template("quote.html").render(**data)
    assert "#" not in html.split("<h1>")[1].split("</h1>")[0]
