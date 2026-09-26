"""Backfill de spools.material_version_id.

material_versions é SCD2 — várias linhas por (material_type, manufacturer,
color), uma marcada is_current. O vínculo certo para uma bobina é a versão
corrente, e só quando ela é única.

O vínculo é de IDENTIDADE, não de preço: o custo da bobina continua vindo do
seu próprio purchased_price / initial_grams.
"""
import importlib
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa

from backend.infra.db import session as session_module
from backend.infra.db.models import MaterialVersion, Spool

_mig = importlib.import_module("migrations.versions.0035_spools_material_version")


async def _bobina(material_type: str, color: str, manufacturer: str) -> Spool:
    async with session_module.SessionFactory() as s:
        sp = Spool(
            material_type=material_type, color=color, manufacturer=manufacturer,
            purchased_at=datetime.now(timezone.utc), purchased_price=Decimal("100"),
            initial_grams=Decimal("1000"), remaining_grams=Decimal("1000"),
        )
        s.add(sp)
        await s.commit()
        await s.refresh(sp)
        return sp


async def _versao(material_type: str, color: str, manufacturer: str,
                  is_current: bool = True) -> MaterialVersion:
    async with session_module.SessionFactory() as s:
        mv = MaterialVersion(
            material_type=material_type, name=f"{material_type} {color}",
            color=color, manufacturer=manufacturer,
            density_g_cm3=Decimal("1.24"), price_per_kg_ref=Decimal("100"),
            is_current=is_current,
        )
        s.add(mv)
        await s.commit()
        await s.refresh(mv)
        return mv


async def _rodar_backfill() -> None:
    async with session_module.SessionFactory() as s:
        await s.execute(sa.text(_mig.BACKFILL_SQL))
        await s.commit()


async def _vinculo(spool_id) -> object:
    async with session_module.SessionFactory() as s:
        return (await s.execute(
            sa.select(Spool.material_version_id).where(Spool.id == spool_id)
        )).scalar_one()


@pytest.mark.asyncio
async def test_casa_com_a_versao_corrente_quando_unica():
    mv = await _versao("PETG", "Azul-035a", "FabX")
    sp = await _bobina("PETG", "Azul-035a", "FabX")
    await _rodar_backfill()
    assert await _vinculo(sp.id) == mv.id


@pytest.mark.asyncio
async def test_ignora_versao_nao_corrente():
    await _versao("ABS", "Cinza-035b", "FabY", is_current=False)
    sp = await _bobina("ABS", "Cinza-035b", "FabY")
    await _rodar_backfill()
    assert await _vinculo(sp.id) is None, (
        "versão fora de is_current não deve ser vinculada"
    )


@pytest.mark.asyncio
async def test_casamento_ambiguo_deixa_nulo():
    # Duas versões correntes para o mesmo trio — não deveria existir, mas o
    # esquema não impede. Escolher uma arbitrariamente é pior que não escolher.
    await _versao("PLA", "Verde-035c", "FabZ")
    await _versao("PLA", "Verde-035c", "FabZ")
    sp = await _bobina("PLA", "Verde-035c", "FabZ")
    await _rodar_backfill()
    assert await _vinculo(sp.id) is None


@pytest.mark.asyncio
async def test_sem_material_correspondente_deixa_nulo():
    sp = await _bobina("TPU", "Cor-que-ninguem-cadastrou-035d", "FabW")
    await _rodar_backfill()
    assert await _vinculo(sp.id) is None


@pytest.mark.asyncio
async def test_e_idempotente():
    mv = await _versao("PLA-CF", "Preto-035e", "FabV")
    sp = await _bobina("PLA-CF", "Preto-035e", "FabV")
    await _rodar_backfill()
    await _rodar_backfill()
    assert await _vinculo(sp.id) == mv.id
