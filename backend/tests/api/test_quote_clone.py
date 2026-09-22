"""Clone de orçamento.

O clone é um orçamento novo que ainda não aconteceu: nasce em rascunho,
sem timestamps de ciclo, sem consumo de material, sem evento de produção
e sem linha no contábil.
"""
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialConsumption, ProductionEvent, Quote, QuoteItem, Sale, User,
)
from backend.settings import get_settings


async def _quote_com_item(kind=QuoteKind.COMMERCIAL, status=QuoteStatus.ENTREGUE) -> Quote:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=kind.value, user_id=u.id, status=status.value,
                  markup_pct=Decimal("80"), min_charge=Decimal("25"),
                  notes="orçamento original", retail_mode=True)
        s.add(q)
        await s.flush()
        s.add(QuoteItem(quote_id=q.id, name="porta-caneta", filename=None,
                        gcode_meta={"filament_m": 12.5, "time_s": 3600, "material": "PLA"},
                        quantity=2, is_multi_color=True,
                        model_source_url="https://printables.com/model/1",
                        model_source_author="alguém", model_source_license="CC-BY"))
        await s.commit()
        await s.refresh(q)
        return q


@pytest.mark.asyncio
async def test_clone_nasce_em_rascunho_sem_timestamps(auth_client):
    orig = await _quote_com_item()
    r = await auth_client.post(f"/quotes/{orig.id}/clone")
    assert r.status_code == 201, r.text
    novo = r.json()
    assert novo["id"] != str(orig.id)
    assert novo["status"] == "draft"
    for campo in ("finalized_at", "approved_at", "produced_at", "delivered_at"):
        assert novo[campo] is None, f"{campo} deveria estar limpo no clone"


@pytest.mark.asyncio
async def test_clone_tem_seq_proprio(auth_client):
    orig = await _quote_com_item()
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    assert novo["seq"] != orig.seq
    assert novo["seq"] > orig.seq


@pytest.mark.asyncio
async def test_clone_copia_config_comercial(auth_client):
    orig = await _quote_com_item()
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    assert Decimal(novo["markup_pct"]) == orig.markup_pct
    assert Decimal(novo["min_charge"]) == orig.min_charge
    assert novo["retail_mode"] == orig.retail_mode
    assert novo["kind"] == orig.kind


@pytest.mark.asyncio
async def test_clone_copia_itens_com_todos_os_campos(auth_client):
    orig = await _quote_com_item()
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    assert len(novo["items"]) == 1
    it = novo["items"][0]
    assert it["name"] == "porta-caneta"
    assert it["quantity"] == 2
    assert it["is_multi_color"] is True
    assert it["gcode_meta"]["filament_m"] == 12.5
    assert it["model_source_url"] == "https://printables.com/model/1"
    assert it["model_source_author"] == "alguém"
    assert it["model_source_license"] == "CC-BY"


@pytest.mark.asyncio
async def test_clone_anota_a_origem_nas_notas(auth_client):
    orig = await _quote_com_item()
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    assert novo["notes"].startswith(f"Clone de #{orig.seq:04d}")
    assert "orçamento original" in novo["notes"]


@pytest.mark.asyncio
async def test_clone_nao_copia_historico_de_producao(auth_client):
    orig = await _quote_com_item()
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    async with session_module.SessionFactory() as s:
        item_ids = (await s.execute(
            sa.select(QuoteItem.id).where(QuoteItem.quote_id == novo["id"]))).scalars().all()
        cons = (await s.execute(sa.select(sa.func.count()).select_from(MaterialConsumption)
                                .where(MaterialConsumption.quote_item_id.in_(item_ids)))).scalar()
        assert cons == 0
        eventos = (await s.execute(sa.select(sa.func.count()).select_from(ProductionEvent)
                                   .where(ProductionEvent.quote_id == novo["id"]))).scalar()
        assert eventos == 0
        vendas = (await s.execute(sa.select(sa.func.count()).select_from(Sale)
                                  .where(Sale.quote_id == novo["id"]))).scalar()
        assert vendas == 0


@pytest.mark.asyncio
async def test_clone_de_pessoal_preserva_tipo(auth_client):
    orig = await _quote_com_item(kind=QuoteKind.PERSONAL, status=QuoteStatus.PRODUZIDO)
    novo = (await auth_client.post(f"/quotes/{orig.id}/clone")).json()
    assert novo["kind"] == "personal"
    assert novo["status"] == "draft"


@pytest.mark.asyncio
async def test_clone_de_orcamento_inexistente_da_404(auth_client):
    import uuid
    r = await auth_client.post(f"/quotes/{uuid.uuid4()}/clone")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_clone_copia_o_arquivo_de_gcode_para_a_pasta_nova(auth_client):
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    conteudo = b"; generated by PrusaSlicer\nG1 X0 Y0\n; filament used [mm] = 12500\n"
    r = await auth_client.post(
        f"/quotes/{qid}/items",
        files={"file": ("peca.gcode", conteudo, "text/plain")},
        data={"name": "peça", "quantity": "1"},
    )
    assert r.status_code == 201, r.text

    novo = (await auth_client.post(f"/quotes/{qid}/clone")).json()
    async with session_module.SessionFactory() as s:
        item = (await s.execute(
            sa.select(QuoteItem).where(QuoteItem.quote_id == novo["id"]))).scalars().one()
    assert item.filename is not None
    base = Path(get_settings().storage_dir)
    assert (base / item.filename).exists(), "arquivo do clone não existe em disco"
    assert novo["id"] in item.filename, "clone aponta para a pasta do original"


@pytest.mark.asyncio
async def test_clone_sem_arquivo_em_disco_nao_falha(auth_client):
    """Histórico anterior ao armazenamento: o registro tem filename mas o
    arquivo sumiu. O clone segue, com o item sem arquivo."""
    orig = await _quote_com_item()
    async with session_module.SessionFactory() as s:
        it = (await s.execute(
            sa.select(QuoteItem).where(QuoteItem.quote_id == orig.id))).scalars().one()
        it.filename = "gcodes/inexistente/sumiu.gcode"
        await s.commit()

    r = await auth_client.post(f"/quotes/{orig.id}/clone")
    assert r.status_code == 201, r.text
    async with session_module.SessionFactory() as s:
        copia = (await s.execute(
            sa.select(QuoteItem).where(QuoteItem.quote_id == r.json()["id"]))).scalars().one()
    assert copia.filename is None
