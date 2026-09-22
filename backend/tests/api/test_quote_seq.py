"""Numeração humana dos orçamentos (#0042).

A suíte roda as migrações contra o banco de teste, então o backfill já
aconteceu quando estes testes rodam — o que eles verificam é o
comportamento da coluna daí em diante.
"""
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, User


async def _novo_quote(status=QuoteStatus.DRAFT) -> Quote:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id, status=status.value,
                  markup_pct=Decimal("100"), min_charge=Decimal("0"))
        s.add(q)
        await s.commit()
        await s.refresh(q)
        return q


@pytest.mark.asyncio
async def test_seq_e_atribuido_pelo_banco_sem_passar_o_campo(auth_client):
    q = await _novo_quote()
    assert q.seq is not None
    assert q.seq > 0


@pytest.mark.asyncio
async def test_seq_incrementa_a_cada_orcamento(auth_client):
    a = await _novo_quote()
    b = await _novo_quote()
    assert b.seq == a.seq + 1


@pytest.mark.asyncio
async def test_seq_e_unico(auth_client):
    a = await _novo_quote()
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        dup = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                    status=QuoteStatus.DRAFT.value, markup_pct=Decimal("0"),
                    min_charge=Decimal("0"), seq=a.seq)
        s.add(dup)
        with pytest.raises(Exception):
            await s.commit()


@pytest.mark.asyncio
async def test_seq_sobrevive_a_delecao_sem_reaproveitar(auth_client):
    a = await _novo_quote()
    async with session_module.SessionFactory() as s:
        obj = await s.get(Quote, a.id)
        await s.delete(obj)
        await s.commit()
    b = await _novo_quote()
    assert b.seq > a.seq


@pytest.mark.asyncio
async def test_criar_via_api_devolve_seq(auth_client):
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    assert r.status_code == 201, r.text
    assert isinstance(r.json()["seq"], int)
    assert r.json()["seq"] > 0


@pytest.mark.asyncio
async def test_listagem_de_quotes_traz_seq(auth_client):
    await auth_client.post("/quotes", json={"kind": "commercial"})
    r = await auth_client.get("/quotes")
    assert r.status_code == 200
    assert all(isinstance(q["seq"], int) for q in r.json())


@pytest.mark.asyncio
async def test_sale_out_traz_quote_seq(auth_client):
    q = await _novo_quote(status=QuoteStatus.APROVADO)
    r = await auth_client.get("/accounting/sales")
    assert r.status_code == 200, r.text
    venda = next(v for v in r.json() if v["quote_id"] == str(q.id))
    assert venda["quote_seq"] == q.seq
