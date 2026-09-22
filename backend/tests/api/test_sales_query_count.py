"""A resolução por linha da listagem de vendas não pode crescer em queries
com o número de linhas.

Antes: sale_items_label e _client_name faziam uma query cada, por linha.
Depois desta task, essas duas viram uma query em lote cada — o custo por
linha vai a zero.

O que este teste NÃO cobre (fora de escopo aqui, de propósito): list_sales
preserva `await sync_sales(session)` (Task 4 não pode remover essa chamada —
isso é da Task 5). sync_sales reprocessa todo orçamento ativo a cada
chamada e faz 2 queries por orçamento (quote_items + quote_services), mesmo
sem nenhum item — um N+1 conhecido, mas *por orçamento ativo*, não por
linha da listagem. O teto abaixo soma esse custo já esperado (2 por
orçamento novo) a uma margem pequena, para isolar o que esta task garante.
Medido nesta mesma configuração: código antigo 19→67 (bate o teto); código
novo 15→39 (dentro do teto, já que os 24 a mais == 2 × 12 orçamentos novos,
100% do sync_sales)."""
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

    # Teto = custo já esperado do sync_sales (2 queries por orçamento ativo
    # novo, fora de escopo desta task) + margem pequena. Qualquer regressão
    # em sale_items_label/_client_name (voltar a 1 query por linha, cada)
    # estoura este teto de sobra — era 48 a mais no código antigo para os
    # mesmos 12 orçamentos, contra 24 esperados só do sync.
    teto = poucas + 2 * novas + 4
    assert muitas <= teto, (
        f"listagem passou de {poucas} para {muitas} queries ao adicionar {novas} vendas "
        f"(teto {teto})"
    )
