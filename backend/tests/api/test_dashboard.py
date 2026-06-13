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


@pytest.mark.asyncio
async def test_dashboard_lists_low_spool_with_material(auth_client):
    """A spool below the low-stock threshold must surface on the dashboard,
    carrying its material so the L3 list can label it."""
    r = await auth_client.post(
        "/spools",
        json={
            "material_type": "PETG",
            "purchased_at": "2026-06-01T00:00:00Z",
            "purchased_price": "100",
            "initial_grams": "1000",
            "remaining_grams": "50",
        },
    )
    assert r.status_code == 201, r.text

    r = await auth_client.get("/dashboard")
    assert r.status_code == 200, r.text
    low = r.json()["lists"]["spools_baixos"]
    assert any(s.get("material_type") == "PETG" for s in low), low
