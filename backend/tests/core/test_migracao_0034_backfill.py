"""Backfill estrutural da 0034.

conftest.py roda `alembic upgrade head` antes de qualquer dado de teste
existir, então não dá para criar dados "antigos" e migrar em cima. O SQL do
backfill vive numa constante da migração e é exercido aqui contra itens
criados pelo ORM — o mesmo SQL que roda em produção.
"""
import importlib
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialVersion, Quote, QuoteItem, QuoteItemFilament, User,
)

_mig = importlib.import_module("migrations.versions.0034_quote_item_filaments")


async def _item_sem_linha(grams_meta: dict) -> tuple[QuoteItem, MaterialVersion]:
    """Cria um QuoteItem direto pelo ORM, sem passar pela rota — que a partir
    da Task 6 criaria a linha 1 automaticamente. É assim que se simula um item
    anterior à migração."""
    async with session_module.SessionFactory() as s:
        u = User(name="u", email="multicor@t.com", password_hash="x")
        s.add(u)
        await s.commit()
        mv = MaterialVersion(
            material_type="PLA", name="PLA Preto", color="Preto",
            manufacturer="ACME", density_g_cm3=Decimal("1.24"),
            price_per_kg_ref=Decimal("100"),
        )
        s.add(mv)
        await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.DRAFT.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q)
        await s.commit()
        it = QuoteItem(quote_id=q.id, name="peça", gcode_meta=grams_meta,
                       material_version_id=mv.id, quantity=2)
        s.add(it)
        await s.commit()
        await s.refresh(it)
        await s.refresh(mv)
        return it, mv


@pytest.mark.asyncio
async def test_backfill_cria_uma_linha_com_gramas_nulas():
    it, mv = await _item_sem_linha({"filament_m": 10, "time_s": 3600})
    async with session_module.SessionFactory() as s:
        await s.execute(sa.text(_mig.BACKFILL_SQL))
        await s.commit()
        linhas = (await s.execute(
            sa.select(QuoteItemFilament)
              .where(QuoteItemFilament.quote_item_id == it.id)
        )).scalars().all()

    assert len(linhas) == 1
    assert linhas[0].position == 1
    assert linhas[0].material_version_id == mv.id
    assert linhas[0].grams_unit is None, (
        "o backfill não deve congelar gramas — NULL significa 'derive do gcode_meta'"
    )


@pytest.mark.asyncio
async def test_backfill_e_idempotente():
    it, _ = await _item_sem_linha({"filament_m": 10, "time_s": 3600})
    async with session_module.SessionFactory() as s:
        await s.execute(sa.text(_mig.BACKFILL_SQL))
        await s.execute(sa.text(_mig.BACKFILL_SQL))
        await s.commit()
        n = (await s.execute(
            sa.select(sa.func.count()).select_from(QuoteItemFilament)
              .where(QuoteItemFilament.quote_item_id == it.id)
        )).scalar_one()
    assert n == 1, "rodar o backfill duas vezes duplicou a linha"


@pytest.mark.asyncio
async def test_item_sem_material_fica_sem_linha_e_sem_erro():
    async with session_module.SessionFactory() as s:
        u = User(name="u", email="multicor2@t.com", password_hash="x")
        s.add(u)
        await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.DRAFT.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q)
        await s.commit()
        it = QuoteItem(quote_id=q.id, name="pendente",
                       gcode_meta={"filament_m": 5, "time_s": 600},
                       material_version_id=None, quantity=1)
        s.add(it)
        await s.commit()
        await s.refresh(it)

        await s.execute(sa.text(_mig.BACKFILL_SQL))   # não deve levantar
        await s.commit()
        n = (await s.execute(
            sa.select(sa.func.count()).select_from(QuoteItemFilament)
              .where(QuoteItemFilament.quote_item_id == it.id)
        )).scalar_one()
    assert n == 0
