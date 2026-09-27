"""Produção com N linhas de filamento: cada cor debita da sua própria bobina,
com a densidade do seu próprio material.

O perigo que esta task existe para eliminar: antes, a densidade vinha do
item (`it.material_version_id`) e o cálculo de gramas cobria o item INTEIRO
— com N cores, cada assignment sem `quote_item_filament_id` debitaria N×
o item da bobina errada, com a densidade errada.
"""
import logging
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.core.pricing.cost import grams_from_meters
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialVersion,
    Quote,
    QuoteItem,
    QuoteItemFilament,
    Spool,
    User,
)

DIAMETER_MM = Decimal("1.75")


def _grams(meters: float, density: Decimal, quantity: int) -> Decimal:
    """Mesma conta que `grams_for_item` faz internamente (sem refugo), para
    prever exatamente o que a produção vai debitar — não uma reimplementação
    independente, e sim o mesmo bloco de baixo nível (`grams_from_meters`)
    que o código de produção usa, só que aplicado à densidade certa para
    provar qual densidade foi realmente usada."""
    per_unit = grams_from_meters(meters, density, DIAMETER_MM)
    return (per_unit * Decimal(quantity)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def _material(nome: str, cor: str, density: str, tipo: str = "PLA") -> MaterialVersion:
    async with session_module.SessionFactory() as s:
        mv = MaterialVersion(
            material_type=tipo, name=nome, color=cor, manufacturer="ACME",
            density_g_cm3=Decimal(density), price_per_kg_ref=Decimal("100"),
            failure_rate_pct=Decimal("0"),
        )
        s.add(mv)
        await s.commit()
        await s.refresh(mv)
        return mv


async def _spool(material_version_id=None, remaining: str = "1000") -> Spool:
    async with session_module.SessionFactory() as s:
        sp = Spool(
            material_type="PLA", purchased_at=datetime.now(timezone.utc),
            purchased_price=Decimal("100.00"), initial_grams=Decimal("1000"),
            remaining_grams=Decimal(remaining), material_version_id=material_version_id,
        )
        s.add(sp)
        await s.commit()
        await s.refresh(sp)
        return sp


async def _quote_multicor_aprovado(
    mv_a: MaterialVersion, mv_b: MaterialVersion, quantity: int,
    grams_unit_a: str | None = None, grams_unit_b: str | None = None,
) -> tuple[Quote, QuoteItem, QuoteItemFilament, QuoteItemFilament]:
    """Orçamento comercial já aprovado com um item de 2 cores — pronto para
    `produce`, sem passar pelas transições HTTP (o que importa aqui é o
    estado das linhas, não o caminho até `aprovado`)."""
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(
            kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
            status=QuoteStatus.APROVADO.value, markup_pct=Decimal("0"),
            min_charge=Decimal("0"),
        )
        s.add(q)
        await s.flush()
        it = QuoteItem(
            quote_id=q.id, name="peça bicolor",
            gcode_meta={"time_s": 3600}, material_version_id=mv_a.id,
            quantity=quantity, is_multi_color=True,
        )
        s.add(it)
        await s.flush()
        fil_a = QuoteItemFilament(
            quote_item_id=it.id, material_version_id=mv_a.id,
            grams_unit=Decimal(grams_unit_a) if grams_unit_a else None, position=1,
        )
        fil_b = QuoteItemFilament(
            quote_item_id=it.id, material_version_id=mv_b.id,
            grams_unit=Decimal(grams_unit_b) if grams_unit_b else None, position=2,
        )
        s.add_all([fil_a, fil_b])
        await s.commit()
        await s.refresh(q)
        await s.refresh(it)
        await s.refresh(fil_a)
        await s.refresh(fil_b)
        return q, it, fil_a, fil_b


@pytest.mark.asyncio
async def test_produzir_multicor_sem_identificar_a_linha_e_409_e_nao_debita(auth_client):
    """O teste que importa: sem `quote_item_filament_id`, um item de 2 linhas
    não pode cair no fallback de gramas do item inteiro — tem que rejeitar
    ANTES de tocar em qualquer bobina."""
    mv_a = await _material("PLA Preto", "Preto", "1.24")
    mv_b = await _material("PLA Dourado", "Dourado", "1.24")
    q, it, fil_a, fil_b = await _quote_multicor_aprovado(
        mv_a, mv_b, quantity=2, grams_unit_a="10", grams_unit_b="8",
    )
    sp_a = await _spool(material_version_id=mv_a.id, remaining="500")
    sp_b = await _spool(material_version_id=mv_b.id, remaining="500")

    async with session_module.SessionFactory() as s:
        saldo_antes = [
            (await s.get(Spool, sp_a.id)).remaining_grams,
            (await s.get(Spool, sp_b.id)).remaining_grams,
        ]

    r = await auth_client.post(
        f"/quotes/{q.id}/transitions/produce",
        json={
            "consumption": [
                {"quote_item_id": str(it.id), "spool_id": str(sp_a.id)},
                {"quote_item_id": str(it.id), "spool_id": str(sp_b.id)},
            ]
        },
    )
    assert r.status_code == 409, r.text
    assert "filamento" in r.text.lower()
    assert "2" in r.text  # menciona o número de linhas

    async with session_module.SessionFactory() as s:
        saldo_depois = [
            (await s.get(Spool, sp_a.id)).remaining_grams,
            (await s.get(Spool, sp_b.id)).remaining_grams,
        ]
    assert saldo_depois == saldo_antes, "debitou estoque antes de rejeitar"

    # E o orçamento continua aprovado — a transição não avançou.
    async with session_module.SessionFactory() as s:
        q_depois = await s.get(Quote, q.id)
        assert q_depois.status == QuoteStatus.APROVADO.value


@pytest.mark.asyncio
async def test_cada_linha_debita_da_sua_bobina_com_a_densidade_do_seu_material(auth_client):
    """Duas cores, duas densidades bem diferentes, quantity > 1: prova que
    cada linha usa a densidade do SEU material — não a do item (que seria
    sempre a da linha 1, `mv_a`).
    """
    mv_a = await _material("PLA Preto", "Preto", "1.24")
    mv_b = await _material("PETG Dourado", "Dourado", "2.40", tipo="PETG")
    quantity = 3
    q, it, fil_a, fil_b = await _quote_multicor_aprovado(mv_a, mv_b, quantity=quantity)
    sp_a = await _spool(material_version_id=mv_a.id, remaining="1000")
    sp_b = await _spool(material_version_id=mv_b.id, remaining="1000")

    meters_a, meters_b = 5.0, 3.0
    r = await auth_client.post(
        f"/quotes/{q.id}/transitions/produce",
        json={
            "consumption": [
                {
                    "quote_item_id": str(it.id), "spool_id": str(sp_a.id),
                    "quote_item_filament_id": str(fil_a.id), "filament_m": meters_a,
                },
                {
                    "quote_item_id": str(it.id), "spool_id": str(sp_b.id),
                    "quote_item_filament_id": str(fil_b.id), "filament_m": meters_b,
                },
            ]
        },
    )
    assert r.status_code == 200, r.text

    esperado_a = _grams(meters_a, mv_a.density_g_cm3, quantity)
    esperado_b = _grams(meters_b, mv_b.density_g_cm3, quantity)
    # Se a densidade viesse do item (bug antigo), a linha 2 usaria a
    # densidade de mv_a em vez da própria (mv_b) — valores bem diferentes
    # o bastante (1.24 vs 2.40) para nunca coincidir por acaso.
    debito_errado_b = _grams(meters_b, mv_a.density_g_cm3, quantity)
    assert esperado_b != debito_errado_b, "densidades escolhidas não distinguem o bug"

    async with session_module.SessionFactory() as s:
        sp_a_depois = await s.get(Spool, sp_a.id)
        sp_b_depois = await s.get(Spool, sp_b.id)

    debito_a = Decimal("1000") - sp_a_depois.remaining_grams
    debito_b = Decimal("1000") - sp_b_depois.remaining_grams
    assert debito_a == esperado_a
    assert debito_b == esperado_b
    assert debito_b != debito_errado_b, "linha 2 debitou com a densidade do item, não a sua"

    # E cada MaterialConsumption gravou a linha (quote_item_filament_id)
    # correspondente — surfaced como `filament_id` no consumo.
    item = (await auth_client.get(f"/quotes/{q.id}")).json()["items"][0]
    by_spool = {c["spool_id"]: c for c in item["consumptions"]}
    assert by_spool[str(sp_a.id)]["filament_id"] == str(fil_a.id)
    assert by_spool[str(sp_b.id)]["filament_id"] == str(fil_b.id)
    assert Decimal(by_spool[str(sp_a.id)]["grams_used"]) == esperado_a
    assert Decimal(by_spool[str(sp_b.id)]["grams_used"]) == esperado_b


@pytest.mark.asyncio
async def test_um_filamento_que_nao_pertence_ao_item_e_400(auth_client):
    mv_a = await _material("PLA A", "A", "1.24")
    mv_b = await _material("PLA B", "B", "1.24")
    q, it, fil_a, _fil_b = await _quote_multicor_aprovado(
        mv_a, mv_b, quantity=1, grams_unit_a="10", grams_unit_b="8",
    )
    outro_mv = await _material("PLA C", "C", "1.24")
    _q2, _it2, outro_fil, _fil2 = await _quote_multicor_aprovado(
        outro_mv, mv_b, quantity=1, grams_unit_a="5", grams_unit_b="5",
    )
    sp = await _spool(material_version_id=mv_a.id, remaining="500")

    r = await auth_client.post(
        f"/quotes/{q.id}/transitions/produce",
        json={
            "consumption": [
                {
                    "quote_item_id": str(it.id), "spool_id": str(sp.id),
                    "quote_item_filament_id": str(outro_fil.id),
                },
            ]
        },
    )
    assert r.status_code == 400, r.text
    assert "não pertence" in r.text.lower()


@pytest.mark.asyncio
async def test_bobina_de_material_divergente_avisa_e_conclui(auth_client, caplog):
    """Bobina com `material_version_id` diferente do material da linha: não
    bloqueia (o backfill da 0035 deixa muita bobina sem material_version_id,
    e bloquear por dado incompleto pararia a produção inteira) — só avisa
    via logger.warning, e a produção conclui normalmente."""
    mv_linha = await _material("PLA Preto", "Preto", "1.24")
    mv_bobina = await _material("PLA Branco", "Branco", "1.24")
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(
            kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
            status=QuoteStatus.APROVADO.value, markup_pct=Decimal("0"),
            min_charge=Decimal("0"),
        )
        s.add(q)
        await s.flush()
        it = QuoteItem(
            quote_id=q.id, name="peça", gcode_meta={"filament_m": 10, "time_s": 3600},
            material_version_id=mv_linha.id, quantity=2,
        )
        s.add(it)
        await s.flush()
        fil = QuoteItemFilament(
            quote_item_id=it.id, material_version_id=mv_linha.id,
            grams_unit=Decimal("10"), position=1,
        )
        s.add(fil)
        await s.commit()
        await s.refresh(it)
        await s.refresh(fil)
    # Bobina de um material DIFERENTE do da linha — a divergência a testar.
    sp = await _spool(material_version_id=mv_bobina.id, remaining="1000")

    with caplog.at_level(logging.WARNING):
        r = await auth_client.post(
            f"/quotes/{q.id}/transitions/produce",
            json={"consumption": [{"quote_item_id": str(it.id), "spool_id": str(sp.id)}]},
        )

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "em_producao"
    assert any(
        "outro material" in rec.getMessage() for rec in caplog.records
    ), "esperava logger.warning avisando sobre material divergente"

    # E a baixa aconteceu de verdade — não é só "não bloqueou".
    item = (await auth_client.get(f"/quotes/{q.id}")).json()["items"][0]
    assert len(item["consumptions"]) == 1
    assert item["consumptions"][0]["filament_id"] == str(fil.id)
    assert item["consumptions"][0]["spool_id"] == str(sp.id)

    async with session_module.SessionFactory() as s:
        sp_depois = await s.get(Spool, sp.id)
    assert sp_depois.remaining_grams < Decimal("1000")


@pytest.mark.asyncio
async def test_duas_cores_falha_e_reproducao_separam_quatro_consumos(auth_client):
    """O caso que motiva `quote_item_filament_id` existir: duas cores no
    mesmo item, produzido, falho, produzido de novo — 4 linhas de
    MaterialConsumption (2 cores × 2 tentativas).

    Nem `filament_id` sozinho nem `consumed_at` sozinho separam as 4: as
    duas linhas de uma MESMA tentativa (mesmo commit) compartilham
    `consumed_at` — só `filament_id` as distingue. As duas linhas de uma
    MESMA cor, em tentativas diferentes, compartilham `filament_id` — só
    `consumed_at` as distingue. É a combinação das duas dimensões que separa
    as 4 linhas.
    """
    mv_a = await _material("PLA Preto", "Preto", "1.24")
    mv_b = await _material("PLA Dourado", "Dourado", "1.24")
    q, it, fil_a, fil_b = await _quote_multicor_aprovado(
        mv_a, mv_b, quantity=1, grams_unit_a="10", grams_unit_b="8",
    )
    sp_a = await _spool(material_version_id=mv_a.id, remaining="1000")
    sp_b = await _spool(material_version_id=mv_b.id, remaining="1000")

    consumo = [
        {"quote_item_id": str(it.id), "spool_id": str(sp_a.id),
         "quote_item_filament_id": str(fil_a.id)},
        {"quote_item_id": str(it.id), "spool_id": str(sp_b.id),
         "quote_item_filament_id": str(fil_b.id)},
    ]

    # 1ª tentativa: produz, depois falha.
    r = await auth_client.post(f"/quotes/{q.id}/transitions/produce",
                               json={"consumption": consumo})
    assert r.status_code == 200, r.text
    r = await auth_client.post(f"/quotes/{q.id}/transitions/fail",
                               json={"failure_description": "entupiu o bico"})
    assert r.status_code == 200, r.text

    # 2ª tentativa: falhou → em_producao de novo, debitando as MESMAS duas
    # bobinas pelas MESMAS duas linhas.
    r = await auth_client.post(f"/quotes/{q.id}/transitions/produce",
                               json={"consumption": consumo})
    assert r.status_code == 200, r.text

    item = (await auth_client.get(f"/quotes/{q.id}")).json()["items"][0]
    consumos = item["consumptions"]
    assert len(consumos) == 4, f"esperava 4 linhas de consumo, veio {len(consumos)}"

    por_filamento: dict[str, list[str]] = {}
    for c in consumos:
        por_filamento.setdefault(c["filament_id"], []).append(c["consumed_at"])

    # Dimensão 1: filament_id separa as duas cores — 2 grupos, cada um com
    # as 2 tentativas daquela cor.
    assert set(por_filamento) == {str(fil_a.id), str(fil_b.id)}, (
        "as 4 linhas não se separaram por cor (filament_id)"
    )
    for fid, timestamps in por_filamento.items():
        assert len(timestamps) == 2, (
            f"cor {fid} devia ter 2 consumos (1 por tentativa), tem {len(timestamps)}"
        )
        # Dimensão 2: dentro da MESMA cor, consumed_at separa as tentativas —
        # se as duas tentativas colidissem no mesmo timestamp, filament_id
        # sozinho não bastaria para saber qual consumo é de qual tentativa.
        assert len(set(timestamps)) == 2, (
            f"cor {fid}: as duas tentativas gravaram o MESMO consumed_at — "
            "impossível separar tentativa 1 de tentativa 2 só por essa cor"
        )

    # E o inverso: consumed_at SOZINHO não separa a cor — as duas cores da
    # MESMA tentativa (mesmo commit) compartilham o timestamp da transação.
    tentativa_1_ts = por_filamento[str(fil_a.id)][0]
    cores_na_tentativa_1 = sorted(
        c["filament_id"] for c in consumos if c["consumed_at"] == tentativa_1_ts
    )
    assert cores_na_tentativa_1 == sorted([str(fil_a.id), str(fil_b.id)]), (
        "consumed_at sozinho já deveria juntar as duas cores da mesma "
        "tentativa — se não juntou, o timestamp não é por-transação como "
        "o teste assume, e a prova de que precisa das duas dimensões cai"
    )
