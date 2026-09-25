"""SaleOut.people — nomes das pessoas atribuídas ao orçamento pessoal.

A coluna "Pessoas" da aba Uso pessoal existia mapeada em client_name, que
é sempre nulo pra orçamento pessoal (não tem cliente). Este teste cobre o
campo people: ambos os nomes atribuídos aparecem, em ordem alfabética, e um
orçamento pessoal sem ninguém atribuído devolve lista vazia (não "—" nem erro
— o "—" é responsabilidade só do frontend).
"""
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Person, Quote, QuotePerson, User


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
async def test_sale_out_traz_nomes_das_pessoas_atribuidas(auth_client):
    pes = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)

    async with session_module.SessionFactory() as s:
        # Nomes fora de ordem alfabética de propósito, pra confirmar que a
        # resposta vem ordenada por nome, não por ordem de inserção.
        zeca = Person(name="Zeca")
        ana = Person(name="Ana")
        s.add_all([zeca, ana])
        await s.flush()
        s.add_all([
            QuotePerson(quote_id=pes.id, person_id=zeca.id),
            QuotePerson(quote_id=pes.id, person_id=ana.id),
        ])
        await s.commit()

    await auth_client.post("/accounting/sync")
    venda = next(v for v in (await auth_client.get("/accounting/sales?kind=personal")).json()
                 if v["quote_id"] == str(pes.id))
    assert venda["people"] == ["Ana", "Zeca"]


@pytest.mark.asyncio
async def test_sale_out_sem_pessoa_atribuida_devolve_lista_vazia(auth_client):
    pes = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    await auth_client.post("/accounting/sync")
    venda = next(v for v in (await auth_client.get("/accounting/sales?kind=personal")).json()
                 if v["quote_id"] == str(pes.id))
    assert venda["people"] == []


@pytest.mark.asyncio
async def test_patch_sale_devolve_people_tambem(auth_client):
    """Mesma classe de bug já corrigida pra produced_on/itens_label/client_name:
    a resposta do PATCH atualiza a linha de forma otimista no frontend, e um
    people ausente/None apagaria a coluna mesmo com pessoas atribuídas."""
    pes = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    async with session_module.SessionFactory() as s:
        ana = Person(name="Ana")
        s.add(ana)
        await s.flush()
        s.add(QuotePerson(quote_id=pes.id, person_id=ana.id))
        await s.commit()

    await auth_client.post("/accounting/sync")
    venda = next(v for v in (await auth_client.get("/accounting/sales?kind=personal")).json()
                 if v["quote_id"] == str(pes.id))

    r = await auth_client.patch(f"/accounting/sales/{venda['id']}", json={"notes": "x"})
    assert r.status_code == 200, r.text
    assert r.json()["people"] == ["Ana"]
