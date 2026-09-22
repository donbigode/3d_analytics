"""Separação de comercial e pessoal no contábil.

O backfill corrige linhas arquivadas (is_stale) criadas antes da coluna
quote_kind existir: elas nasceram com o server_default 'commercial' e
nunca são re-sincronizadas, porque sync_sales ignora quem saiu dos
status ativos.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import MaterialConsumption, Quote, QuoteItem, Sale, Spool, User


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


@pytest.mark.asyncio
async def test_filtro_kind_separa_as_listas(auth_client):
    com = await _quote(QuoteKind.COMMERCIAL, QuoteStatus.APROVADO)
    pes = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    await auth_client.post("/accounting/sync")

    r = await auth_client.get("/accounting/sales?kind=commercial")
    ids = {v["quote_id"] for v in r.json()}
    assert str(com.id) in ids
    assert str(pes.id) not in ids

    r = await auth_client.get("/accounting/sales?kind=personal")
    ids = {v["quote_id"] for v in r.json()}
    assert str(pes.id) in ids
    assert str(com.id) not in ids


@pytest.mark.asyncio
async def test_sem_kind_devolve_ambos(auth_client):
    com = await _quote(QuoteKind.COMMERCIAL, QuoteStatus.APROVADO)
    pes = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    await auth_client.post("/accounting/sync")
    ids = {v["quote_id"] for v in (await auth_client.get("/accounting/sales")).json()}
    assert {str(com.id), str(pes.id)} <= ids


@pytest.mark.asyncio
async def test_sale_out_traz_quote_kind_e_produced_on(auth_client):
    pes = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    await auth_client.post("/accounting/sync")
    venda = next(v for v in (await auth_client.get("/accounting/sales")).json()
                 if v["quote_id"] == str(pes.id))
    assert venda["quote_kind"] == "personal"
    # Sem baixa de material, produced_on é nulo — o DRE cai no created_at.
    assert "produced_on" in venda
    assert venda["produced_on"] is None


@pytest.mark.asyncio
async def test_produced_on_e_a_menor_data_de_baixa_de_material(auth_client):
    """Com baixa de material, produced_on = min(consumed_at).date() — mesmo
    critério que _perda_operacional usa no DRE (backend/core/accounting/dre.py).
    Cobre tanto a listagem quanto o PATCH, que devem concordar."""
    pes = await _quote(QuoteKind.PERSONAL, QuoteStatus.PRODUZIDO)
    mais_cedo = datetime(2026, 6, 5, tzinfo=timezone.utc)
    mais_tarde = mais_cedo + timedelta(days=2)
    async with session_module.SessionFactory() as s:
        item = QuoteItem(quote_id=pes.id, name="Vaso", gcode_meta={"filament_g": 10}, quantity=1)
        spool = Spool(material_type="PLA", color="Verde", purchased_at=mais_cedo,
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("900"))
        s.add_all([item, spool])
        await s.flush()
        s.add_all([
            MaterialConsumption(quote_item_id=item.id, spool_id=spool.id,
                               grams_used=Decimal("50"), unit_cost_snapshot=Decimal("0.10"),
                               consumed_at=mais_tarde),
            MaterialConsumption(quote_item_id=item.id, spool_id=spool.id,
                               grams_used=Decimal("20"), unit_cost_snapshot=Decimal("0.10"),
                               consumed_at=mais_cedo),
        ])
        await s.commit()

    await auth_client.post("/accounting/sync")
    venda = next(v for v in (await auth_client.get("/accounting/sales")).json()
                 if v["quote_id"] == str(pes.id))
    assert venda["produced_on"] == mais_cedo.date().isoformat()

    # PATCH também precisa devolver produced_on — não pode voltar None e
    # apagar a coluna numa atualização otimista de UI.
    r = await auth_client.patch(f"/accounting/sales/{venda['id']}", json={"notes": "x"})
    assert r.status_code == 200, r.text
    assert r.json()["produced_on"] == mais_cedo.date().isoformat()
