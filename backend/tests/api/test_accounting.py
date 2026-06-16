from decimal import Decimal

import pytest

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, User


async def _seed_commercial_quote() -> str:
    import sqlalchemy as sa
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.APROVADO.value, markup_pct=Decimal("100"),
                  min_charge=Decimal("0"))
        s.add(q); await s.commit()
        return str(q.id)


@pytest.mark.asyncio
async def test_sales_listed_after_sync_and_patch(auth_client):
    await _seed_commercial_quote()
    # GET dispara o sync e materializa a venda
    r = await auth_client.get("/accounting/sales")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    sale = rows[0]
    assert sale["is_sold"] is False

    # confirmar a venda
    r = await auth_client.patch(f"/accounting/sales/{sale['id']}", json={
        "is_sold": True, "confirmed_revenue": "1234.00", "sold_at": "2026-06-10",
    })
    assert r.status_code == 200, r.text
    assert r.json()["is_sold"] is True
    assert r.json()["confirmed_revenue"] == "1234.00"


@pytest.mark.asyncio
async def test_confirming_sale_backfills_revenue_and_date(auth_client):
    """Confirmar a venda sem (ou com null explícito) receita/data preenche
    defaults a partir de quote_total/hoje — nunca deixa venda vendida sem receita."""
    await _seed_commercial_quote()
    sale = (await auth_client.get("/accounting/sales")).json()[0]
    quote_total = sale["quote_total"]

    r = await auth_client.patch(f"/accounting/sales/{sale['id']}", json={
        "is_sold": True, "confirmed_revenue": None, "sold_at": None,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_sold"] is True
    assert body["confirmed_revenue"] == quote_total
    assert body["sold_at"] is not None


@pytest.mark.asyncio
async def test_expenses_crud(auth_client):
    r = await auth_client.post("/accounting/expenses", json={
        "category": "parts", "description": "bico 0.4", "amount": "40.00",
        "incurred_at": "2026-06-12",
    })
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    r = await auth_client.get("/accounting/expenses")
    assert any(e["id"] == eid for e in r.json())
    r = await auth_client.patch(f"/accounting/expenses/{eid}", json={"amount": "55.00"})
    assert r.json()["amount"] == "55.00"
    r = await auth_client.delete(f"/accounting/expenses/{eid}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_dre_shape(auth_client):
    r = await auth_client.get("/accounting/dre?from=2026-06-01&to=2026-06-30")
    assert r.status_code == 200, r.text
    for key in ["receita_bruta", "cpv", "custos_variaveis", "lucro_bruto",
                "despesas", "resultado_liquido", "margem_liquida_pct"]:
        assert key in r.json()


@pytest.mark.asyncio
async def test_dre_v2_shape(auth_client):
    r = await auth_client.get("/accounting/dre?from=2026-06-01&to=2026-06-30")
    assert r.status_code == 200, r.text
    for key in ["impostos", "receita_liquida", "custo_estoque"]:
        assert key in r.json()


@pytest.mark.asyncio
async def test_expense_equipment_and_recurring(auth_client):
    r = await auth_client.post("/accounting/expenses", json={
        "category": "equipment", "description": "Impressora X1", "amount": "3000.00",
        "incurred_at": "2026-06-01", "is_recurring": False,
    })
    assert r.status_code == 201, r.text
    assert r.json()["category"] == "equipment"
    r = await auth_client.post("/accounting/expenses", json={
        "category": "other", "description": "Internet", "amount": "100.00",
        "incurred_at": "2026-06-01", "is_recurring": True,
    })
    assert r.json()["is_recurring"] is True


@pytest.mark.asyncio
async def test_dre_monthly_shape(auth_client):
    r = await auth_client.get("/accounting/dre/monthly?from=2026-01-01&to=2026-02-28")
    assert r.status_code == 200, r.text
    assert [x["month"] for x in r.json()] == ["2026-01", "2026-02"]
