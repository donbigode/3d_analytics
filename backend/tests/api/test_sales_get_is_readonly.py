"""GET não escreve. Antes, list_sales chamava sync_sales() com commit —
cada clique em 'vendido' recalculava o custo de todo orçamento aprovado.
"""
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, Sale, User


@pytest.mark.asyncio
async def test_get_sales_nao_materializa_venda(auth_client):
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        s.add(Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                    status=QuoteStatus.APROVADO.value, markup_pct=Decimal("100"),
                    min_charge=Decimal("0")))
        await s.commit()

    r = await auth_client.get("/accounting/sales")
    assert r.status_code == 200
    assert r.json() == [], "GET materializou a venda — deveria ser só leitura"

    await auth_client.post("/accounting/sync")
    assert len((await auth_client.get("/accounting/sales")).json()) == 1


@pytest.mark.asyncio
async def test_get_sales_nao_altera_updated_at(auth_client):
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        s.add(Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                    status=QuoteStatus.APROVADO.value, markup_pct=Decimal("100"),
                    min_charge=Decimal("0")))
        await s.commit()
    await auth_client.post("/accounting/sync")

    async with session_module.SessionFactory() as s:
        antes = (await s.execute(sa.select(Sale.updated_at))).scalars().all()
    await auth_client.get("/accounting/sales")
    async with session_module.SessionFactory() as s:
        depois = (await s.execute(sa.select(Sale.updated_at))).scalars().all()
    assert antes == depois
