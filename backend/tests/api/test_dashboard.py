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


@pytest.mark.asyncio
async def test_dashboard_receita_from_confirmed_sale(auth_client):
    """Receita do dashboard vem da venda confirmada, não do status do orçamento."""
    from datetime import date
    from decimal import Decimal
    from backend.core.models import QuoteKind, QuoteStatus
    from backend.infra.db import session as session_module
    from backend.infra.db.models import Quote, Sale, User
    import sqlalchemy as sa

    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        s.add(Sale(quote_id=q.id, quote_status="entregue", quote_total=Decimal("500"),
                   cpv_calc=Decimal("100"), is_sold=True, confirmed_revenue=Decimal("777"),
                   variable_costs=Decimal("0"), sold_at=date.today()))
        await s.commit()

    r = await auth_client.get("/dashboard")
    assert r.status_code == 200, r.text
    assert r.json()["cards"]["receita"] == "777.00"
