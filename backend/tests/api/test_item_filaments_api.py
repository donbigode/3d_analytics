"""Custo e contrato das linhas de filamento, pela API.

Pelo HTTP de propósito: é onde o N+1 e a serialização aparecem, e é o que a
tela consome.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from backend.core.models import QuoteKind, QuoteStatus, SpoolStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialVersion,
    Quote,
    QuoteItem,
    QuoteItemFilament,
    Settings,
    Spool,
    User,
    WatcherInboxFile,
)

GCODE = b";TIME:3600\n;Filament used:5.0m\n;Material Type:PLA\n"


async def _settings() -> Settings:
    """Linha de settings conhecida.

    O conftest de `api/` limpa a tabela `settings` depois de cada teste, então
    o valor semeado pela migração não sobrevive — sem semear aqui o esperado
    dependeria dos defaults transitórios de `_get_settings_row`.
    """
    async with session_module.SessionFactory() as s:
        st = Settings(
            id=1,
            energy_kwh_price=Decimal("0.95"),
            printer_power_w=Decimal("150"),
            printer_depreciation_per_hour=Decimal("2"),
            printer_maintenance_per_hour=Decimal("0"),
        )
        s.add(st)
        await s.commit()
        await s.refresh(st)
        return st


async def _material(nome: str, preco: str, cor: str, tipo: str = "PLA") -> MaterialVersion:
    async with session_module.SessionFactory() as s:
        mv = MaterialVersion(
            material_type=tipo, name=nome, color=cor, manufacturer="ACME",
            density_g_cm3=Decimal("1.24"), price_per_kg_ref=Decimal(preco),
            failure_rate_pct=Decimal("0"),
        )
        s.add(mv)
        await s.commit()
        await s.refresh(mv)
        return mv


async def _quote_com_item_multicor(mv_a: MaterialVersion, mv_b: MaterialVersion,
                                   quantity: int) -> Quote:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.DRAFT.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q)
        await s.commit()
        it = QuoteItem(quote_id=q.id, name="peça bicolor",
                       gcode_meta={"filament_m": 10, "time_s": 3600},
                       material_version_id=mv_a.id, quantity=quantity,
                       is_multi_color=True)
        s.add(it)
        await s.commit()
        s.add_all([
            QuoteItemFilament(quote_item_id=it.id, material_version_id=mv_a.id,
                              grams_unit=Decimal("12"), position=1),
            QuoteItemFilament(quote_item_id=it.id, material_version_id=mv_b.id,
                              grams_unit=Decimal("8"), position=2),
        ])
        await s.commit()
        await s.refresh(q)
        return q


@pytest.mark.asyncio
async def test_subtotal_soma_as_duas_cores_e_conta_o_tempo_uma_vez(auth_client):
    from backend.core.pricing.cost import depreciation_cost, energy_cost, filament_cost
    from backend.core.pricing.failure import apply_failure

    st = await _settings()
    mv_a = await _material("PLA Preto", "100", "Preto")
    mv_b = await _material("PLA Dourado", "250", "Dourado")
    q = await _quote_com_item_multicor(mv_a, mv_b, quantity=3)

    r = await auth_client.get(f"/quotes/{q.id}")
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]

    # As duas linhas aparecem, ordenadas por position
    assert [f["grams_unit"] for f in item["filaments"]] == ["12.00", "8.00"]
    assert [f["material_name"] for f in item["filaments"]] == ["PLA Preto", "PLA Dourado"]
    assert [f["position"] for f in item["filaments"]] == [1, 2]

    # E o subtotal soma o filamento das duas, com o tempo contado uma vez.
    # Gramas digitadas não levam refugo, então `is_multi_color` não infla nada
    # aqui — é exatamente o ponto de gravar as gramas por linha.
    fil = filament_cost(Decimal("12"), Decimal("100")) + filament_cost(Decimal("8"), Decimal("250"))
    en = energy_cost(3600, st.printer_power_w, st.energy_kwh_price)
    dep = depreciation_cost(3600, st.printer_depreciation_per_hour)
    # apply_failure arredonda a base antes da quantidade — mesma ordem de
    # compute_item_cost, senão o esperado divergiria por centavos.
    esperado = apply_failure(fil + en + dep, Decimal("0")) * Decimal(3)

    assert Decimal(item["subtotal"]) == esperado.quantize(Decimal("0.01")), (
        "subtotal divergiu — conferir se energia/depreciação foram somadas por cor"
    )


@pytest.mark.asyncio
async def test_item_criado_pela_rota_nasce_com_linha_e_orca(auth_client):
    """Invariante 1 pela porta da frente: item com material resolvido tem linha.

    Sem isto `_build_item_input` devolveria None e o item pararia de orçar em
    silêncio — que é exatamente o risco desta task.
    """
    await _settings()
    await _material("PLA Preto", "100", "Preto")   # único PLA → auto-resolve

    r = await auth_client.post("/quotes", json={"kind": "commercial", "markup_pct": "0"})
    assert r.status_code == 201, r.text
    qid = r.json()["id"]

    r = await auth_client.post(
        f"/quotes/{qid}/items",
        data={"name": "peça", "quantity": "1"},
        files={"file": ("p.gcode", GCODE, "text/plain")},
    )
    assert r.status_code == 201, r.text
    item = r.json()["items"][0]
    assert item["material_pending"] is False
    assert len(item["filaments"]) == 1
    assert item["filaments"][0]["position"] == 1
    # grams_unit None = "derive do gcode_meta" — a linha nasce sem gramas fixas
    assert item["filaments"][0]["grams_unit"] is None
    assert Decimal(item["subtotal"]) > 0, "item novo parou de orçar"


@pytest.mark.asyncio
async def test_resolver_material_pendente_cria_a_linha(auth_client):
    """Item que entra pendente não tem linha; resolver o material cria a linha 1."""
    await _settings()
    # Dois PLA registrados → nada de auto-resolve, o item entra pendente
    await _material("PLA Preto", "100", "Preto")
    mv_branco = await _material("PLA Branco", "110", "Branco")

    r = await auth_client.post("/quotes", json={"kind": "commercial", "markup_pct": "0"})
    qid = r.json()["id"]
    r = await auth_client.post(
        f"/quotes/{qid}/items",
        data={"name": "peça", "quantity": "1"},
        files={"file": ("p.gcode", GCODE, "text/plain")},
    )
    assert r.status_code == 201, r.text
    item = r.json()["items"][0]
    assert item["material_pending"] is True
    assert item["filaments"] == [], "item pendente não deve nascer com linha"
    assert Decimal(item["subtotal"]) == 0

    # Finalizar deve ser bloqueado enquanto não há linha
    r = await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    assert r.status_code == 409, r.text

    r = await auth_client.put(f"/quotes/{qid}/items/{item['id']}",
                              json={"material_id": str(mv_branco.id)})
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert len(item["filaments"]) == 1
    assert item["filaments"][0]["material_id"] == str(mv_branco.id)
    assert Decimal(item["subtotal"]) > 0

    r = await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_material_pending_segue_a_linha_nao_o_material_version_id(auth_client):
    """`material_pending` e o custo têm que usar O MESMO critério: ter linha.

    Item com `material_version_id` preenchido e nenhuma linha é o estado que o
    caminho de escrita da Task 7 pode produzir (apagar a última linha). Se a
    tela continuasse lendo `material_version_id`, ela mostraria a peça como
    resolvida enquanto `_build_item_input` devolvia None e o subtotal ia a zero
    em silêncio — os dois critérios divergindo sem ninguém perceber.
    """
    await _settings()
    mv = await _material("PLA Preto", "100", "Preto")

    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.DRAFT.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q)
        await s.flush()
        s.add(QuoteItem(quote_id=q.id, name="peça sem linha",
                        gcode_meta={"filament_m": 10, "time_s": 3600, "material": "PLA"},
                        material_version_id=mv.id, quantity=1))
        await s.commit()
        qid = str(q.id)

    r = await auth_client.get(f"/quotes/{qid}")
    assert r.status_code == 200, r.text
    corpo = r.json()
    item = corpo["items"][0]

    # material_id segue preenchido (é o derivado), mas pendente é quem não tem linha
    assert item["material_id"] == str(mv.id)
    assert item["filaments"] == []
    assert item["material_pending"] is True, (
        "material_pending ainda está lendo material_version_id — divergiu do custo"
    )
    assert item["pending_material_code"] == "PLA"
    assert Decimal(item["subtotal"]) == 0
    assert corpo["pending_items"] == 1

    # E o mesmo critério barra o finalize
    r = await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_trocar_material_reaproveita_a_linha_1(auth_client):
    """Trocar o material não duplica a linha 1 — atualiza a existente."""
    await _settings()
    mv_a = await _material("PLA Preto", "100", "Preto")
    mv_b = await _material("PETG Azul", "200", "Azul", tipo="PETG")

    r = await auth_client.post("/quotes", json={"kind": "commercial", "markup_pct": "0"})
    qid = r.json()["id"]
    r = await auth_client.post(
        f"/quotes/{qid}/items",
        data={"name": "peça", "quantity": "1"},
        files={"file": ("p.gcode", GCODE, "text/plain")},
    )
    item = r.json()["items"][0]
    assert item["filaments"][0]["material_id"] == str(mv_a.id)

    r = await auth_client.put(f"/quotes/{qid}/items/{item['id']}",
                              json={"material_id": str(mv_b.id)})
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert len(item["filaments"]) == 1, "troca de material duplicou a linha"
    assert item["filaments"][0]["material_id"] == str(mv_b.id)
    assert item["material_id"] == str(mv_b.id)


@pytest.mark.asyncio
async def test_clone_preserva_as_duas_cores_e_continua_orcando(auth_client):
    await _settings()
    mv_a = await _material("PLA Preto", "100", "Preto")
    mv_b = await _material("PLA Dourado", "250", "Dourado")
    q = await _quote_com_item_multicor(mv_a, mv_b, quantity=2)

    r = await auth_client.post(f"/quotes/{q.id}/clone")
    assert r.status_code == 201, r.text
    clone = r.json()
    assert len(clone["items"]) == 1
    item = clone["items"][0]
    assert [(f["material_id"], f["grams_unit"], f["position"]) for f in item["filaments"]] == [
        (str(mv_a.id), "12.00", 1),
        (str(mv_b.id), "8.00", 2),
    ]
    assert Decimal(item["subtotal"]) > 0, "clone perdeu as linhas e parou de orçar"

    # E o original continua com as suas linhas (nada foi movido)
    r = await auth_client.get(f"/quotes/{q.id}")
    assert len(r.json()["items"][0]["filaments"]) == 2


@pytest.mark.asyncio
async def test_item_vindo_do_inbox_nasce_com_linha(auth_client):
    await _settings()
    mv = await _material("PLA Preto", "100", "Preto")

    async with session_module.SessionFactory() as s:
        rec = WatcherInboxFile(
            file_hash="hash-item-filaments-1",
            original_path="/tmp/peca.gcode",
            parsed_meta={"time_s": 3600, "filament_m": 10, "material": "PLA"},
        )
        s.add(rec)
        await s.commit()
        rec_id = str(rec.id)

    r = await auth_client.post(f"/inbox/{rec_id}/promote", json={"kind": "commercial"})
    assert r.status_code == 200, r.text
    qid = r.json()["id"]

    r = await auth_client.get(f"/quotes/{qid}")
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert len(item["filaments"]) == 1
    assert item["filaments"][0]["material_id"] == str(mv.id)
    assert Decimal(item["subtotal"]) > 0, "item do inbox nasceu sem linha e não orça"


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


async def _quote_com_n_itens(mv_a: MaterialVersion, mv_b: MaterialVersion,
                             n_itens: int, linhas_por_item: int) -> Quote:
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.DRAFT.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q)
        await s.flush()
        for i in range(n_itens):
            it = QuoteItem(quote_id=q.id, name=f"peça {i}",
                           gcode_meta={"filament_m": 10, "time_s": 3600},
                           material_version_id=mv_a.id, quantity=1,
                           is_multi_color=linhas_por_item > 1)
            s.add(it)
            await s.flush()
            for pos in range(1, linhas_por_item + 1):
                s.add(QuoteItemFilament(
                    quote_item_id=it.id,
                    material_version_id=(mv_a.id if pos == 1 else mv_b.id),
                    grams_unit=Decimal("10"), position=pos,
                ))
        await s.commit()
        await s.refresh(q)
        return q


@pytest.mark.asyncio
async def test_queries_nao_crescem_com_itens_e_linhas(auth_client):
    """As linhas vêm numa query só — nem por item, nem por linha.

    Buscar as linhas dentro do laço de custo reintroduziria o N+1 que a Spec 2
    tirou do contábil, e aqui seria pior: o cálculo percorre todos os itens.

    Medido: 1 item/1 linha = 9 queries, 3 itens/2 linhas = 9 queries. Igualdade
    exata, não teto com folga, de propósito: o diferencial de um N+1 aqui é 2
    queries (o orçamento pequeno ganharia 1, o grande 3), então qualquer folga
    de 2 esconderia exatamente o bug que o teste existe para pegar — era o caso
    do `teto = poucas + 2` copiado de test_sales_query_count.py, onde a folga
    discrimina só porque o diferencial de linhas de lá é muito maior.
    """
    await _settings()
    mv_a = await _material("PLA Preto", "100", "Preto")
    mv_b = await _material("PLA Dourado", "250", "Dourado")

    pequeno = await _quote_com_n_itens(mv_a, mv_b, n_itens=1, linhas_por_item=1)
    grande = await _quote_com_n_itens(mv_a, mv_b, n_itens=3, linhas_por_item=2)

    poucas = await _contar_queries(auth_client, f"/quotes/{pequeno.id}")
    muitas = await _contar_queries(auth_client, f"/quotes/{grande.id}")

    assert muitas == poucas, (
        f"GET /quotes passou de {poucas} para {muitas} queries ao ir de 1 item/1 linha "
        f"para 3 itens/2 linhas — as linhas voltaram a ser buscadas por item"
    )


@pytest.mark.asyncio
async def test_filaments_e_material_id_no_mesmo_patch_e_400(auth_client):
    mv_a = await _material("PLA A", "100", "A-400")
    mv_b = await _material("PLA B", "100", "B-400")
    q = await _quote_com_item_multicor(mv_a, mv_b, quantity=1)
    r0 = await auth_client.get(f"/quotes/{q.id}")
    item_id = r0.json()["items"][0]["id"]

    r = await auth_client.put(
        f"/quotes/{q.id}/items/{item_id}",
        json={"material_id": str(mv_b.id),
              "filaments": [{"material_id": str(mv_a.id), "grams_unit": "10"}]},
    )
    assert r.status_code == 400
    assert "material_id" in r.text

    # As linhas originais continuam intactas — a rejeição não deve ter escrito nada.
    r2 = await auth_client.get(f"/quotes/{q.id}")
    item = r2.json()["items"][0]
    assert [f["material_id"] for f in item["filaments"]] == [str(mv_a.id), str(mv_b.id)]
    assert [f["grams_unit"] for f in item["filaments"]] == ["12.00", "8.00"]


@pytest.mark.asyncio
async def test_patch_sem_filaments_preserva_as_linhas(auth_client):
    """A regressão óbvia é tratar None como lista vazia e apagar tudo."""
    mv_a = await _material("PLA A", "100", "A-401")
    mv_b = await _material("PLA B", "100", "B-401")
    q = await _quote_com_item_multicor(mv_a, mv_b, quantity=1)
    r0 = await auth_client.get(f"/quotes/{q.id}")
    item_id = r0.json()["items"][0]["id"]

    r = await auth_client.put(f"/quotes/{q.id}/items/{item_id}", json={"name": "novo nome"})
    assert r.status_code == 200
    item = [i for i in r.json()["items"] if i["id"] == item_id][0]
    assert item["name"] == "novo nome"
    assert len(item["filaments"]) == 2, "o PATCH apagou as linhas"
    assert [f["material_id"] for f in item["filaments"]] == [str(mv_a.id), str(mv_b.id)]


@pytest.mark.asyncio
async def test_material_id_sozinho_reescreve_a_linha_1_sem_duplicar(auth_client):
    mv_a = await _material("PLA A", "100", "A-402")
    mv_b = await _material("PLA B", "100", "B-402")
    q = await _quote_com_item_multicor(mv_a, mv_b, quantity=1)
    r0 = await auth_client.get(f"/quotes/{q.id}")
    item_id = r0.json()["items"][0]["id"]
    mv_c = await _material("PLA C", "100", "C-402")

    r = await auth_client.put(f"/quotes/{q.id}/items/{item_id}",
                              json={"material_id": str(mv_c.id)})
    assert r.status_code == 200
    item = [i for i in r.json()["items"] if i["id"] == item_id][0]
    assert len(item["filaments"]) == 2
    assert item["filaments"][0]["material_id"] == str(mv_c.id)
    assert item["material_id"] == str(mv_c.id), "o derivado não acompanhou a linha 1"


@pytest.mark.asyncio
async def test_lista_vazia_e_rejeitada(auth_client):
    mv_a = await _material("PLA A", "100", "A-403")
    mv_b = await _material("PLA B", "100", "B-403")
    q = await _quote_com_item_multicor(mv_a, mv_b, quantity=1)
    r0 = await auth_client.get(f"/quotes/{q.id}")
    item_id = r0.json()["items"][0]["id"]

    r = await auth_client.put(f"/quotes/{q.id}/items/{item_id}", json={"filaments": []})
    assert r.status_code == 400
    assert "pelo menos um filamento" in r.text

    r2 = await auth_client.get(f"/quotes/{q.id}")
    item = r2.json()["items"][0]
    assert len(item["filaments"]) == 2, "a rejeição não devia ter apagado as linhas"


@pytest.mark.asyncio
async def test_duas_linhas_sem_gramas_sao_rejeitadas(auth_client):
    mv_a = await _material("PLA A", "100", "A-404")
    mv_b = await _material("PLA B", "100", "B-404")
    q = await _quote_com_item_multicor(mv_a, mv_b, quantity=1)
    r0 = await auth_client.get(f"/quotes/{q.id}")
    item_id = r0.json()["items"][0]["id"]

    r = await auth_client.put(
        f"/quotes/{q.id}/items/{item_id}",
        json={"filaments": [{"material_id": str(mv_a.id)},
                            {"material_id": str(mv_b.id)}]},
    )
    assert r.status_code == 400
    assert "gramas" in r.text

    r2 = await auth_client.get(f"/quotes/{q.id}")
    item = r2.json()["items"][0]
    assert [f["grams_unit"] for f in item["filaments"]] == ["12.00", "8.00"], (
        "a rejeição não devia ter tocado as linhas existentes"
    )


@pytest.mark.asyncio
async def test_grams_unit_zero_e_422_nao_400(auth_client):
    """`gt=0` é validação de schema (Pydantic), não regra de negócio — 422, não 400.

    E a rejeição não pode ter escrito a linha com gramas zeradas.
    """
    mv_a = await _material("PLA A", "100", "A-407")
    mv_b = await _material("PLA B", "100", "B-407")
    q = await _quote_com_item_multicor(mv_a, mv_b, quantity=1)
    r0 = await auth_client.get(f"/quotes/{q.id}")
    item_id = r0.json()["items"][0]["id"]

    r = await auth_client.put(
        f"/quotes/{q.id}/items/{item_id}",
        json={"filaments": [{"material_id": str(mv_a.id), "grams_unit": "0"},
                            {"material_id": str(mv_b.id), "grams_unit": "5"}]},
    )
    assert r.status_code == 422, r.text

    r2 = await auth_client.get(f"/quotes/{q.id}")
    item = r2.json()["items"][0]
    assert [f["grams_unit"] for f in item["filaments"]] == ["12.00", "8.00"], (
        "o 422 não devia ter escrito nada"
    )


@pytest.mark.asyncio
async def test_remover_a_linha_do_meio_renumera(auth_client):
    mv_a = await _material("PLA A", "100", "A-405")
    mv_b = await _material("PLA B", "100", "B-405")
    mv_c = await _material("PLA C", "100", "C-405")
    q = await _quote_com_item_multicor(mv_a, mv_b, quantity=1)
    r0 = await auth_client.get(f"/quotes/{q.id}")
    item_id = r0.json()["items"][0]["id"]

    # três linhas, depois remove a do meio mandando a lista sem ela
    await auth_client.put(f"/quotes/{q.id}/items/{item_id}", json={"filaments": [
        {"material_id": str(mv_a.id), "grams_unit": "10"},
        {"material_id": str(mv_b.id), "grams_unit": "5"},
        {"material_id": str(mv_c.id), "grams_unit": "2"},
    ]})
    r = await auth_client.put(f"/quotes/{q.id}/items/{item_id}", json={"filaments": [
        {"material_id": str(mv_a.id), "grams_unit": "10"},
        {"material_id": str(mv_c.id), "grams_unit": "2"},
    ]})
    assert r.status_code == 200
    item = [i for i in r.json()["items"] if i["id"] == item_id][0]
    assert [f["position"] for f in item["filaments"]] == [1, 2]
    assert [f["material_id"] for f in item["filaments"]] == [str(mv_a.id), str(mv_c.id)]


@pytest.mark.asyncio
async def test_item_novo_ja_nasce_com_a_linha_1(auth_client):
    """add_item resolve o material e precisa criar a linha, senão o item nasce
    violando a invariante 1 e não orça."""
    # Dois PLA registrados → auto-resolve não escolhe nenhum e o item nasce
    # pendente — precisa do PUT para resolver, como a tela faz.
    await _material("PLA Outro", "90", "Outro-406")
    mv = await _material("PLA Novo", "100", "Novo-406")
    # Mesmo caminho que a tela usa para adicionar item manual: POST é form
    # data (name/quantity/file opcionais), e sem `file` o item nasce pendente
    # — então resolvemos o material com o PUT, como a tela faz.
    r = await auth_client.post("/quotes", json={"kind": "commercial", "markup_pct": "0"})
    assert r.status_code == 201, r.text
    qid = r.json()["id"]

    r = await auth_client.post(
        f"/quotes/{qid}/items",
        data={"name": "peça manual", "quantity": "1"},
    )
    assert r.status_code == 201, r.text
    item = r.json()["items"][0]
    assert item["material_pending"] is True
    assert item["filaments"] == [], "item pendente não deve nascer com linha"

    r = await auth_client.put(f"/quotes/{qid}/items/{item['id']}",
                              json={"material_id": str(mv.id)})
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert len(item["filaments"]) == 1
    assert item["filaments"][0]["position"] == 1
    assert item["filaments"][0]["material_id"] == str(mv.id), (
        "resolver o material pendente não criou/atualizou a linha 1"
    )


async def _spool(material_type: str) -> Spool:
    """Bobina aberta de um tipo — o alvo do filtro da tela de produzir."""
    async with session_module.SessionFactory() as s:
        sp = Spool(
            material_type=material_type, color="Preto", manufacturer="ACME",
            purchased_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
            remaining_grams=Decimal("1000"), status=SpoolStatus.OPEN.value,
        )
        s.add(sp)
        await s.commit()
        await s.refresh(sp)
        return sp


async def _item_com_material_cru(material_cru: str) -> tuple[Quote, QuoteItem]:
    """Item cujo `gcode_meta["material"]` é a string crua do fatiador.

    É o estado normal de um item vindo de gcode: o fatiador escreve o nome
    comercial do filamento, que não é um `material_type` cadastrado.
    """
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.DRAFT.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q)
        await s.commit()
        it = QuoteItem(quote_id=q.id, name="peça",
                       gcode_meta={"filament_m": 10, "time_s": 3600,
                                   "material": material_cru},
                       quantity=1)
        s.add(it)
        await s.commit()
        await s.refresh(q)
        await s.refresh(it)
        return q, it


@pytest.mark.asyncio
async def test_escolher_material_pelas_linhas_normaliza_gcode_meta_material(auth_client):
    """Escrever `filaments` tem que normalizar `gcode_meta["material"]`.

    O branch de `material_id` já fazia isso; o de `filaments` não, e aí escolher
    material pela tela nova deixava a string crua do fatiador no campo. Nove
    consumidores leem `gcode_meta["material"]` — entre eles o `material_polymer`
    do PDF, os prompts de markup/variantes e o filtro de bobina da tela de
    produzir. Este teste afirma o campo E a consequência: a bobina volta a casar.
    """
    await _settings()
    mv = await _material("PETG Preto", "120", "Preto", tipo="PETG")
    sp = await _spool("PETG")
    q, it = await _item_com_material_cru("Generic PLA")

    # Antes: a string do fatiador não é um material_type, então o filtro da
    # tela de produzir (`sp.material_type === matCode`) não casa com nada.
    r = await auth_client.get(f"/quotes/{q.id}")
    assert r.status_code == 200, r.text
    antes = r.json()["items"][0]["gcode_meta"]["material"]
    assert antes == "Generic PLA"
    assert antes != sp.material_type, "o teste precisa começar sem casar"

    r = await auth_client.put(
        f"/quotes/{q.id}/items/{it.id}",
        json={"filaments": [{"material_id": str(mv.id)}]},
    )
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]

    # Depois: o campo guarda o material_type do material escolhido…
    assert item["gcode_meta"]["material"] == "PETG"
    # …e é por isso que a bobina volta a casar. Sem esta segunda asserção, o
    # teste passaria mesmo com o campo escrito com a grafia errada (o nome do
    # produto, "PETG Preto", em vez do material_type).
    assert item["gcode_meta"]["material"] == sp.material_type

    # E persistiu de verdade no JSONB, não só na resposta desta requisição.
    r = await auth_client.get(f"/quotes/{q.id}")
    assert r.json()["items"][0]["gcode_meta"]["material"] == "PETG"


@pytest.mark.asyncio
async def test_normalizacao_usa_a_linha_1_nao_a_ultima(auth_client):
    """Num item de duas cores, o material do item é o da linha 1.

    O `mv` do loop da rota é o da ÚLTIMA linha, então usá-lo seria gravar o
    polímero da cor 2 como material do item. Tipos distintos de propósito: com
    dois PLA o teste passaria de qualquer jeito.
    """
    await _settings()
    mv_1 = await _material("PETG Preto", "120", "Preto", tipo="PETG")
    mv_2 = await _material("ABS Vermelho", "90", "Vermelho", tipo="ABS")
    q, it = await _item_com_material_cru("Generic PLA")

    r = await auth_client.put(
        f"/quotes/{q.id}/items/{it.id}",
        json={"filaments": [
            {"material_id": str(mv_1.id), "grams_unit": "12.00"},
            {"material_id": str(mv_2.id), "grams_unit": "8.00"},
        ]},
    )
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert [f["position"] for f in item["filaments"]] == [1, 2]
    assert item["gcode_meta"]["material"] == "PETG", (
        "gravou o polímero da última linha, não o da linha 1"
    )

    # Inverter a ordem das linhas troca qual é a linha 1 — e o campo segue.
    r = await auth_client.put(
        f"/quotes/{q.id}/items/{it.id}",
        json={"filaments": [
            {"material_id": str(mv_2.id), "grams_unit": "8.00"},
            {"material_id": str(mv_1.id), "grams_unit": "12.00"},
        ]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["gcode_meta"]["material"] == "ABS"


@pytest.mark.asyncio
async def test_escrever_filaments_nao_apaga_o_resto_do_gcode_meta(auth_client):
    """Só a chave `material` muda: o dict é reatribuído, não substituído.

    `filament_m` e `time_s` são o custo do item. Se a normalização trocasse o
    gcode_meta por `{"material": ...}`, o subtotal iria a zero em silêncio.
    """
    await _settings()
    mv = await _material("PETG Preto", "120", "Preto", tipo="PETG")
    q, it = await _item_com_material_cru("Generic PLA")

    r = await auth_client.put(
        f"/quotes/{q.id}/items/{it.id}",
        json={"filaments": [{"material_id": str(mv.id)}]},
    )
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["gcode_meta"]["filament_m"] == 10
    assert item["gcode_meta"]["time_s"] == 3600
    assert Decimal(item["subtotal"]) > 0, "o item parou de orçar"


@pytest.mark.asyncio
async def test_filaments_e_material_code_no_mesmo_patch_e_400(auth_client):
    """O guard cobria `material_id` e deixava `material_code` passar.

    São três jeitos de dizer qual é o material do item, e o guard existe porque
    dois juntos obrigam alguém a adivinhar qual ganha. Aqui ganhava o último por
    acidente da ordem dos branches: `filaments` gravava as linhas e normalizava
    `gcode_meta["material"]`, e o `elif material_code` em seguida reescrevia a
    linha 1 e sobrescrevia o mesmo campo com o código cru.
    """
    await _settings()
    # Exatamente UM PLA registrado, para `material_code: "PLA"` resolver. Sem
    # isso a rota devolveria 400 pelo "cannot uniquely resolve" e o teste
    # passaria pelo motivo errado — verde com o guard ausente.
    await _material("PLA Único", "100", "Preto", tipo="PLA")
    mv_petg = await _material("PETG Preto", "120", "Preto", tipo="PETG")
    mv_abs = await _material("ABS Vermelho", "90", "Vermelho", tipo="ABS")
    q, it = await _item_com_material_cru("Generic PLA")

    # Estado de partida: uma linha PETG e o campo já normalizado.
    r = await auth_client.put(
        f"/quotes/{q.id}/items/{it.id}",
        json={"filaments": [{"material_id": str(mv_petg.id)}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["gcode_meta"]["material"] == "PETG"

    # Os dois juntos: a lista pediria ABS, o atalho pediria PLA.
    r = await auth_client.put(
        f"/quotes/{q.id}/items/{it.id}",
        json={"material_code": "PLA",
              "filaments": [{"material_id": str(mv_abs.id)}]},
    )
    assert r.status_code == 400, r.text
    assert "material_code" in r.text

    # E nada foi escrito: nem a lista (seria ABS), nem o campo (seria "PLA").
    # Só o status não bastaria — a rejeição vinha depois de escrever a linha 1.
    r = await auth_client.get(f"/quotes/{q.id}")
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert [f["material_id"] for f in item["filaments"]] == [str(mv_petg.id)], (
        "a rejeição escreveu as linhas antes de levantar"
    )
    assert item["gcode_meta"]["material"] == "PETG", (
        "a rejeição sobrescreveu gcode_meta['material'] antes de levantar"
    )
