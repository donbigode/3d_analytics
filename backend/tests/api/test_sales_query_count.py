"""A resolução por linha da listagem de vendas não pode crescer em queries
com o número de linhas.

Antes: sale_items_label e _client_name faziam uma query cada, por linha.
Essas duas viram uma query em lote cada — o custo por linha vai a zero.

Até a Task 5, `list_sales` também chamava `sync_sales(session)` dentro do
GET, e sync_sales reprocessa todo orçamento ativo a cada chamada (2 queries
por orçamento, mesmo sem nenhum item) — um termo linear que dependia de
quantos orçamentos novos o teste semeasse, não da listagem em si. A Task 5
tirou o sync do GET (agora é explícito via POST /accounting/sync, chamado
antes de cada medição abaixo), então esse termo linear não existe mais: o
teto volta a ser uma constante pequena.
Medido nesta configuração: poucas=6, muitas=6 ao adicionar 12 vendas — sem
crescimento. Teto = poucas + 2 (folga pequena, sem termo por orçamento)."""
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Client, Quote, User


async def _semear(n: int) -> None:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        for i in range(n):
            c = Client(name=f"cliente {i}")
            s.add(c)
            await s.flush()
            s.add(Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id, client_id=c.id,
                        status=QuoteStatus.APROVADO.value, markup_pct=Decimal("100"),
                        min_charge=Decimal("0")))
        await s.commit()


async def _contar_queries(auth_client, url: str) -> int:
    contador = {"n": 0}

    def antes(conn, cursor, statement, params, context, executemany):
        contador["n"] += 1

    event.listen(session_module.engine.sync_engine, "before_cursor_execute", antes)
    try:
        r = await auth_client.get(url)
        assert r.status_code == 200, r.text
    finally:
        event.remove(session_module.engine.sync_engine, "before_cursor_execute", antes)
    return contador["n"]


@pytest.mark.asyncio
async def test_queries_nao_crescem_com_o_numero_de_vendas(auth_client):
    await _semear(3)
    await auth_client.post("/accounting/sync")
    poucas = await _contar_queries(auth_client, "/accounting/sales?kind=commercial")

    novas = 12
    await _semear(novas)
    await auth_client.post("/accounting/sync")
    muitas = await _contar_queries(auth_client, "/accounting/sales?kind=commercial")

    # Sem sync dentro do GET (Task 5), a listagem não tem mais termo linear
    # no número de orçamentos — só a margem pequena de sempre. Qualquer
    # regressão em sale_items_label/_client_name (voltar a 1 query por
    # linha, cada) estoura este teto de sobra: medido poucas=6, muitas=6
    # (nenhum crescimento) ao adicionar 12 vendas.
    teto = poucas + 2
    assert muitas <= teto, (
        f"listagem passou de {poucas} para {muitas} queries ao adicionar {novas} vendas "
        f"(teto {teto})"
    )
