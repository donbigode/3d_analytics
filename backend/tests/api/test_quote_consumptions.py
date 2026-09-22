"""O filamento realmente consumido sobe para a API.

O dado já existia em material_consumptions — bobina, gramas, custo
congelado e data — e nunca chegava à tela: depois do rascunho, a coluna
Material mostrava só o polímero do gcode ("PLA").
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialConsumption, Quote, QuoteItem, Spool, User,
)


async def _quote_com_consumo(n_consumos: int = 1):
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        sp = Spool(material_type="PLA", color="Preto", manufacturer="Voolt3D",
                   purchased_at=datetime.now(timezone.utc), purchased_price=Decimal("100.00"),
                   initial_grams=Decimal("1000"), remaining_grams=Decimal("900"))
        s.add(sp)
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.PRODUZIDO.value, markup_pct=Decimal("100"),
                  min_charge=Decimal("0"))
        s.add(q)
        await s.flush()
        it = QuoteItem(quote_id=q.id, name="porta-caneta",
                       gcode_meta={"filament_m": 12.5, "material": "PLA"}, quantity=1)
        s.add(it)
        await s.flush()
        base = datetime(2026, 9, 12, tzinfo=timezone.utc)
        for i in range(n_consumos):
            s.add(MaterialConsumption(
                quote_item_id=it.id, spool_id=sp.id, grams_used=Decimal("48.20"),
                unit_cost_snapshot=Decimal("0.1000"),
                consumed_at=base + timedelta(days=2 * i),
            ))
        await s.commit()
        return q, it, sp


@pytest.mark.asyncio
async def test_rascunho_vem_sem_consumos(auth_client):
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    await auth_client.post(f"/quotes/{qid}/items", data={"name": "peça", "quantity": "1"})
    item = (await auth_client.get(f"/quotes/{qid}")).json()["items"][0]
    assert item["consumptions"] == []


@pytest.mark.asyncio
async def test_consumo_traz_bobina_gramas_e_custo(auth_client):
    q, it, sp = await _quote_com_consumo()
    item = (await auth_client.get(f"/quotes/{q.id}")).json()["items"][0]
    assert len(item["consumptions"]) == 1
    c = item["consumptions"][0]
    assert c["spool_id"] == str(sp.id)
    assert c["material_type"] == "PLA"
    assert c["color"] == "Preto"
    assert c["manufacturer"] == "Voolt3D"
    assert Decimal(c["grams_used"]) == Decimal("48.20")
    assert Decimal(c["unit_cost_snapshot"]) == Decimal("0.1000")
    assert Decimal(c["custo_total"]) == Decimal("4.82")
    assert "PLA" in c["spool_label"] and "Preto" in c["spool_label"]


@pytest.mark.asyncio
async def test_reimpressao_gera_duas_linhas_ordenadas(auth_client):
    """Falhou → reproduziu consome material duas vezes. Hoje a tela não
    registra nenhuma das duas."""
    q, _it, _sp = await _quote_com_consumo(n_consumos=2)
    item = (await auth_client.get(f"/quotes/{q.id}")).json()["items"][0]
    assert len(item["consumptions"]) == 2
    datas = [c["consumed_at"] for c in item["consumptions"]]
    assert datas == sorted(datas), "consumos devem vir em ordem cronológica"


@pytest.mark.asyncio
async def test_custo_congelado_nao_muda_quando_a_bobina_encarece(auth_client):
    q, _it, sp = await _quote_com_consumo()
    async with session_module.SessionFactory() as s:
        bobina = await s.get(Spool, sp.id)
        bobina.purchased_price = Decimal("300.00")
        await s.commit()
    item = (await auth_client.get(f"/quotes/{q.id}")).json()["items"][0]
    assert Decimal(item["consumptions"][0]["unit_cost_snapshot"]) == Decimal("0.1000")


@pytest.mark.asyncio
async def test_consumos_nao_reintroduzem_n_mais_1(auth_client):
    from sqlalchemy import event

    q, it, sp = await _quote_com_consumo()
    async with session_module.SessionFactory() as s:
        for i in range(6):
            extra = QuoteItem(quote_id=q.id, name=f"peça {i}",
                              gcode_meta={"filament_m": 5.0}, quantity=1)
            s.add(extra)
            await s.flush()
            s.add(MaterialConsumption(quote_item_id=extra.id, spool_id=sp.id,
                                      grams_used=Decimal("10"),
                                      unit_cost_snapshot=Decimal("0.1")))
        await s.commit()

    contador = {"n": 0}

    def antes(conn, cursor, statement, params, context, executemany):
        contador["n"] += 1

    event.listen(session_module.engine.sync_engine, "before_cursor_execute", antes)
    try:
        r = await auth_client.get(f"/quotes/{q.id}")
        assert r.status_code == 200
    finally:
        event.remove(session_module.engine.sync_engine, "before_cursor_execute", antes)

    assert contador["n"] < 20, (
        f"{contador['n']} queries para 7 itens — consumos estão sendo buscados por item"
    )
