"""Separação de comercial e pessoal no contábil.

O backfill corrige linhas arquivadas (is_stale) criadas antes da coluna
quote_kind existir: elas nasceram com o server_default 'commercial' e
nunca são re-sincronizadas, porque sync_sales ignora quem saiu dos
status ativos.
"""
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, Sale, User


async def _quote(kind: QuoteKind, status: QuoteStatus) -> Quote:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=kind.value, user_id=u.id, status=status.value,
                  markup_pct=Decimal("100"), min_charge=Decimal("0"))
        s.add(q)
        await s.commit()
        await s.refresh(q)
        return q


@pytest.mark.asyncio
async def test_backfill_corrige_linha_arquivada_com_kind_errado(auth_client):
    q = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    await auth_client.post("/accounting/sync")

    # Simula o estado legado: linha arquivada marcada como comercial.
    async with session_module.SessionFactory() as s:
        sale = (await s.execute(sa.select(Sale).where(Sale.quote_id == q.id))).scalars().one()
        sale.quote_kind = QuoteKind.COMMERCIAL.value
        sale.is_stale = True
        await s.commit()

    # Aplicar o mesmo UPDATE da migração.
    async with session_module.SessionFactory() as s:
        await s.execute(sa.text(
            "UPDATE sales s SET quote_kind = q.kind FROM quotes q "
            "WHERE q.id = s.quote_id AND s.quote_kind IS DISTINCT FROM q.kind"
        ))
        await s.commit()
        corrigida = (await s.execute(sa.select(Sale).where(Sale.quote_id == q.id))).scalars().one()
        assert corrigida.quote_kind == QuoteKind.PERSONAL.value


@pytest.mark.asyncio
async def test_backfill_e_idempotente(auth_client):
    await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    await auth_client.post("/accounting/sync")
    sql = sa.text(
        "UPDATE sales s SET quote_kind = q.kind FROM quotes q "
        "WHERE q.id = s.quote_id AND s.quote_kind IS DISTINCT FROM q.kind"
    )
    async with session_module.SessionFactory() as s:
        await s.execute(sql)
        await s.commit()
        r2 = await s.execute(sql)
        await s.commit()
        assert r2.rowcount == 0, "segunda execução deveria não tocar em nada"
