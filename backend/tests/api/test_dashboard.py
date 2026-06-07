import pytest


@pytest.mark.asyncio
async def test_dashboard_shape(auth_client):
    r = await auth_client.get("/dashboard")
    assert r.status_code == 200
    body = r.json()
    for key in ["cards", "charts", "lists"]:
        assert key in body
    cards = body["cards"]
    for c in ["receita", "despesa", "lucro", "margem_pct", "gasto_pessoal",
              "orcamentos_por_estado", "taxa_conversao_pct", "estoque"]:
        assert c in cards
    for chart in ["receita_vs_despesa", "funil", "despesa_categorias", "orcado_vs_real"]:
        assert chart in body["charts"]
    for lst in ["ultimos_orcamentos", "parados", "spools_baixos", "inbox"]:
        assert lst in body["lists"]
