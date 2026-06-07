from backend.infra.pdf.render import render_quote_pdf


def test_render_pdf_basic():
    data = {
        "business_name": "Test", "business_tagline": None, "logo_url": None,
        "brand_color": "#111827", "currency": "BRL",
        "quote": {"id": "abc", "kind": "commercial", "status": "orcado", "client": "Ana"},
        "items": [{"name": "Peca A", "filament_m": 5.0, "time_s": 1800, "qty": 1, "subtotal": 25.0}],
        "services": [{"name": "Slicing", "qty": 5, "rate": 1.0, "subtotal": 5.0}],
        "totals": {"cost": 30.0, "markup_pct": 50, "min_charge": 0, "total": 45.0},
    }
    pdf = render_quote_pdf(data)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
