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


def test_pdf_de_uma_cor_nao_mudou():
    # Guarda de regressão do Task 9: item de uma linha (o caso majoritário)
    # tem que renderizar exatamente como antes — sem lista, sem <br>, sem
    # repetir o material. "PLA Preto" precisa aparecer uma única vez.
    data = _base_data({"id": "abc", "seq": 1, "kind": "commercial", "status": "orcado", "client": "Ana"})
    data["items"] = [{
        "name": "Peca A", "filament_m": 5.0, "time_s": 1800, "qty": 1, "subtotal": 25.0,
        "material_name": "PLA Preto", "material_color": None, "material_polymer": None,
        "is_multi_color": False,
        "filaments": [{"material_name": "PLA Preto", "material_color": None, "grams_unit": 20.0}],
    }]
    html = _env.get_template("quote.html").render(**data)
    assert html.count("PLA Preto") == 1
    assert "<br>" not in html
    # Se o macro entrasse no ramo de lista por engano (ex.: threshold trocado
    # para ">= 1" em vez de "> 1"), as gramas apareceriam coladas ao nome —
    # e hoje elas não aparecem nessa célula.
    assert "20.00" not in html


def test_pdf_multicor_lista_as_cores():
    # Três cores com nomes e gramas distintos e não-substring entre si, para
    # que uma asserção não passe encontrando a cor errada.
    data = _base_data({"id": "abc", "seq": 2, "kind": "commercial", "status": "orcado", "client": "Ana"})
    data["items"] = [{
        "name": "Peca B", "filament_m": 5.0, "time_s": 1800, "qty": 1, "subtotal": 25.0,
        "filaments": [
            {"material_name": "PLA Vermelho", "material_color": None, "grams_unit": 12.5},
            {"material_name": "PETG Azul Marinho", "material_color": None, "grams_unit": 33.75},
            {"material_name": "ABS Cinza Grafite", "material_color": None, "grams_unit": 4.2},
        ],
    }]
    html = _env.get_template("quote.html").render(**data)
    for name in ("PLA Vermelho", "PETG Azul Marinho", "ABS Cinza Grafite"):
        assert html.count(name) == 1
    assert "12.50 g" in html
    assert "33.75 g" in html
    assert "4.20 g" in html
    # Três linhas de cor = dois <br> entre elas.
    assert html.count("<br>") == 2


def test_retail_mode_lista_cores_sem_gramas():
    # retail_mode já esconde metragem e tempo — a cor é informação de
    # produto, não de custo, então o nome aparece; a grama, não.
    data = _base_data({"id": "abc", "seq": 3, "kind": "commercial", "status": "orcado", "client": "Ana"})
    data["retail_mode"] = True
    data["total_pieces"] = 1
    data["price_per_piece"] = 25.0
    data["items"] = [{
        "name": "Peca C", "filament_m": 5.0, "time_s": 1800, "qty": 1, "subtotal": 25.0,
        "client_price": 25.0, "client_price_per_piece": 25.0,
        "filaments": [
            {"material_name": "PLA Verde Limão", "material_color": None, "grams_unit": 8.4},
            {"material_name": "TPU Roxo Escuro", "material_color": None, "grams_unit": 15.9},
        ],
    }]
    html = _env.get_template("quote.html").render(**data)
    assert "PLA Verde Limão" in html
    assert "TPU Roxo Escuro" in html
    # As gramas não podem vazar em modo retail.
    assert "8.40" not in html
    assert "15.90" not in html
