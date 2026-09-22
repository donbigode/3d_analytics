"""Data de venda é escolha explícita, não efeito colateral do clique.

Antes: marcar is_sold gravava date.today() escondido, e o item caía no
mês corrente do DRE mesmo tendo sido vendido em outro.
"""
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Quote, User


async def _venda(auth_client) -> dict:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.APROVADO.value, markup_pct=Decimal("100"),
                  min_charge=Decimal("0"))
        s.add(q)
        await s.commit()
    await auth_client.post("/accounting/sync")
    return (await auth_client.get("/accounting/sales?kind=commercial")).json()[0]


@pytest.mark.asyncio
async def test_confirmar_sem_data_e_rejeitado(auth_client):
    v = await _venda(auth_client)
    r = await auth_client.patch(f"/accounting/sales/{v['id']}", json={"is_sold": True})
    assert r.status_code == 422, r.text
    assert "data" in r.text.lower()


@pytest.mark.asyncio
async def test_confirmar_com_data_nula_explicita_e_rejeitado(auth_client):
    v = await _venda(auth_client)
    r = await auth_client.patch(f"/accounting/sales/{v['id']}",
                                json={"is_sold": True, "sold_at": None})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_data_informada_e_gravada_sem_substituicao(auth_client):
    v = await _venda(auth_client)
    r = await auth_client.patch(f"/accounting/sales/{v['id']}",
                                json={"is_sold": True, "sold_at": "2026-03-15"})
    assert r.status_code == 200, r.text
    assert r.json()["sold_at"] == "2026-03-15"


@pytest.mark.asyncio
async def test_receita_ainda_ganha_default_do_total(auth_client):
    """A receita tem palpite óbvio; a data não. Só a data virou obrigatória."""
    v = await _venda(auth_client)
    r = await auth_client.patch(f"/accounting/sales/{v['id']}",
                                json={"is_sold": True, "sold_at": "2026-03-15"})
    assert r.json()["confirmed_revenue"] == v["quote_total"]


@pytest.mark.asyncio
async def test_desmarcar_limpa_data_e_receita(auth_client):
    v = await _venda(auth_client)
    await auth_client.patch(f"/accounting/sales/{v['id']}",
                            json={"is_sold": True, "sold_at": "2026-03-15"})
    r = await auth_client.patch(f"/accounting/sales/{v['id']}", json={"is_sold": False})
    assert r.status_code == 200, r.text
    assert r.json()["sold_at"] is None
    assert r.json()["confirmed_revenue"] is None


@pytest.mark.asyncio
async def test_remarcar_apos_desmarcar_exige_data_de_novo(auth_client):
    """Regressão do estado fantasma: antes, remarcar ressuscitava a data velha."""
    v = await _venda(auth_client)
    await auth_client.patch(f"/accounting/sales/{v['id']}",
                            json={"is_sold": True, "sold_at": "2026-03-15"})
    await auth_client.patch(f"/accounting/sales/{v['id']}", json={"is_sold": False})
    r = await auth_client.patch(f"/accounting/sales/{v['id']}", json={"is_sold": True})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_patch_devolve_linha_completa(auth_client):
    """A tela usa a resposta do PATCH para atualizar a linha sem recarregar —
    se vier incompleta, as colunas esvaziam."""
    v = await _venda(auth_client)
    r = await auth_client.patch(f"/accounting/sales/{v['id']}",
                                json={"is_sold": True, "sold_at": "2026-03-15"})
    body = r.json()
    assert "itens_label" in body
    assert "client_name" in body
    assert isinstance(body["quote_seq"], int)
