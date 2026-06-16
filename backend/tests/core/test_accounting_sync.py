from decimal import Decimal

import pytest
from sqlalchemy import select

from backend.core.accounting.sync import sync_sales
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, Sale, User


async def _mk_quote(s, user, status, kind=QuoteKind.COMMERCIAL):
    q = Quote(kind=kind.value, user_id=user.id, status=status.value,
              markup_pct=Decimal("100"), min_charge=Decimal("0"))
    s.add(q); await s.commit()
    return q


@pytest.mark.asyncio
async def test_sync_creates_preserves_and_marks_stale():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="sync@t.com", password_hash="x")
        s.add(user); await s.commit()
        q_appr = await _mk_quote(s, user, QuoteStatus.APROVADO)
        q_pers = await _mk_quote(s, user, QuoteStatus.PRODUZIDO, kind=QuoteKind.PERSONAL)

    # 1º sync: cria linha só para o comercial; ignora o pessoal
    async with session_module.SessionFactory() as s:
        res = await sync_sales(s)
        assert res["created"] == 1
        sales = (await s.execute(select(Sale))).scalars().all()
        assert len(sales) == 1
        sale = sales[0]
        assert sale.quote_id == q_appr.id
        assert sale.is_sold is False
        # usuário confirma a venda na mão
        sale.is_sold = True
        sale.confirmed_revenue = Decimal("999")
        await s.commit()

    # 2º sync: preserva os editáveis, atualiza espelho
    async with session_module.SessionFactory() as s:
        res = await sync_sales(s)
        assert res["created"] == 0 and res["updated"] == 1
        sale = (await s.execute(select(Sale))).scalars().one()
        assert sale.is_sold is True
        assert sale.confirmed_revenue == Decimal("999")

    # orçamento sai de aprovado+ -> linha vira stale
    async with session_module.SessionFactory() as s:
        q = await s.get(Quote, q_appr.id)
        q.status = QuoteStatus.CANCELADO.value
        await s.commit()
        res = await sync_sales(s)
        assert res["stale"] == 1
        sale = (await s.execute(select(Sale))).scalars().one()
        assert sale.is_stale is True
        assert sale.confirmed_revenue == Decimal("999")
