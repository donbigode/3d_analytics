import pytest


@pytest.mark.asyncio
async def test_spools_crud_and_adjust(auth_client):
    r = await auth_client.post("/spools", json={
        "material_type": "PLA",
        "purchased_from": "Acme",
        "purchased_at": "2026-06-01T00:00:00Z",
        "purchased_price": "100",
        "initial_grams": "1000",
        "remaining_grams": "1000",
    })
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = await auth_client.get("/spools")
    assert any(s["id"] == sid for s in r.json())

    r = await auth_client.get(f"/spools/{sid}")
    assert r.status_code == 200

    r = await auth_client.put(f"/spools/{sid}", json={"remaining_grams": "500"})
    assert r.status_code == 200
    assert r.json()["remaining_grams"] == "500.00"

    r = await auth_client.delete(f"/spools/{sid}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_spool_stores_color_and_manufacturer(auth_client):
    """A physical spool carries its color and manufacturer so the stock table
    can show them; both are editable and persist independently."""
    r = await auth_client.post("/spools", json={
        "material_type": "PLA",
        "color": "Galáxia",
        "manufacturer": "3D Lab",
        "purchased_at": "2026-06-01T00:00:00Z",
        "purchased_price": "100",
        "initial_grams": "1000",
        "remaining_grams": "1000",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["color"] == "Galáxia"
    assert body["manufacturer"] == "3D Lab"
    sid = body["id"]

    r = await auth_client.put(f"/spools/{sid}", json={"color": "Preto"})
    assert r.status_code == 200, r.text
    assert r.json()["color"] == "Preto"
    assert r.json()["manufacturer"] == "3D Lab"  # untouched by partial update


@pytest.mark.asyncio
async def test_delete_consumed_spool_returns_409(auth_client):
    """A spool already debited by a produced quote can't be hard-deleted —
    it would orphan the consumption history. Expect a friendly 409, not a 500."""
    await auth_client.post(
        "/materials",
        json={
            "material_type": "PLA",
            "name": "PLA",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "100",
            "failure_rate_pct": "0",
        },
    )
    r = await auth_client.post("/spools", json={
        "material_type": "PLA",
        "purchased_at": "2026-06-01T00:00:00Z",
        "purchased_price": "100",
        "initial_grams": "1000",
        "remaining_grams": "1000",
    })
    sid = r.json()["id"]

    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("x.gcode", b";TIME:60\n;Filament used:5.0m\n;Material Type:PLA\n",
                      "application/octet-stream")}
    await auth_client.post(f"/quotes/{qid}/items", files=files,
                           data={"name": "X", "quantity": "1"})
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    await auth_client.post(f"/quotes/{qid}/transitions/approve")
    item_id = (await auth_client.get(f"/quotes/{qid}")).json()["items"][0]["id"]
    await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]},
    )

    r = await auth_client.delete(f"/spools/{sid}")
    assert r.status_code == 409, r.text
    # still retrievable — delete was refused, not half-applied
    assert (await auth_client.get(f"/spools/{sid}")).status_code == 200


@pytest.mark.asyncio
async def test_spool_remaining_cannot_exceed_initial(auth_client):
    r = await auth_client.post("/spools", json={
        "material_type": "PLA",
        "purchased_at": "2026-06-01T00:00:00Z",
        "purchased_price": "100",
        "initial_grams": "1000",
        "remaining_grams": "1500",
    })
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_spool_out_exposes_material_version_id(auth_client):
    """O `SpoolOut` carrega o vínculo com o produto — é ele que a tela de
    produzir usa para pré-selecionar a bobina da cor de cada linha.

    As DUAS asserções importam: só a de vinculada passaria com o campo cravado
    em `None`, e só a de não-vinculada passaria com o campo cravado em qualquer
    id. O `material_type` das duas é igual de propósito — é o casamento frouxo
    que a pré-seleção NÃO deve usar, e a única coisa que as distingue é o
    vínculo.
    """
    from datetime import datetime, timezone
    from decimal import Decimal

    from backend.infra.db import session as session_module
    from backend.infra.db.models import MaterialVersion, Spool

    # Grava direto no banco (não pela API) para controlar exatamente qual
    # spool fica vinculada e qual não, sem depender do auto-resolve de
    # `POST /spools` — esse caminho tem teste próprio logo abaixo.
    async with session_module.SessionFactory() as s:
        mv = MaterialVersion(
            material_type="PLA", name="PLA Preto", color="Preto", manufacturer="ACME",
            density_g_cm3=Decimal("1.24"), price_per_kg_ref=Decimal("100"),
            failure_rate_pct=Decimal("0"),
        )
        s.add(mv)
        await s.flush()
        vinculada = Spool(
            material_type="PLA", color="Preto", purchased_at=datetime.now(timezone.utc),
            purchased_price=Decimal("100.00"), initial_grams=Decimal("1000"),
            remaining_grams=Decimal("1000"), material_version_id=mv.id,
        )
        solta = Spool(
            material_type="PLA", color="Preto", purchased_at=datetime.now(timezone.utc),
            purchased_price=Decimal("100.00"), initial_grams=Decimal("1000"),
            remaining_grams=Decimal("1000"), material_version_id=None,
        )
        s.add_all([vinculada, solta])
        await s.commit()
        mv_id, com_id, sem_id = str(mv.id), str(vinculada.id), str(solta.id)

    r = await auth_client.get(f"/spools/{com_id}")
    assert r.status_code == 200, r.text
    assert r.json()["material_version_id"] == mv_id

    r = await auth_client.get(f"/spools/{sem_id}")
    assert r.status_code == 200, r.text
    assert r.json()["material_version_id"] is None

    # E na listagem, que é de onde a tela de produzir lê.
    por_id = {s["id"]: s for s in (await auth_client.get("/spools")).json()}
    assert por_id[com_id]["material_version_id"] == mv_id
    assert por_id[sem_id]["material_version_id"] is None


@pytest.mark.asyncio
async def test_spool_criada_com_trio_unico_e_auto_vinculada(auth_client):
    """`POST /spools` sem `material_version_id`: casamento único de
    (material_type, color, manufacturer) contra a versão CORRENTE vincula
    sozinho — mesma regra da migração 0035, agora no caminho de escrita.
    """
    r = await auth_client.post("/materials", json={
        "material_type": "PLA", "name": "PLA Preto ACME",
        "manufacturer": "ACME", "color": "Preto",
        "density_g_cm3": "1.24", "price_per_kg_ref": "100",
    })
    assert r.status_code == 201, r.text
    mv_id = r.json()["id"]

    r = await auth_client.post("/spools", json={
        "material_type": "PLA", "manufacturer": "ACME", "color": "Preto",
        "purchased_at": "2026-06-01T00:00:00Z",
        "purchased_price": "100", "initial_grams": "1000", "remaining_grams": "1000",
    })
    assert r.status_code == 201, r.text
    assert r.json()["material_version_id"] == mv_id


@pytest.mark.asyncio
async def test_spool_criada_com_trio_ambiguo_fica_sem_vinculo(auth_client):
    """Dois materiais correntes casam o mesmo trio (type/color/manufacturer)
    — escolher um dos dois seria vincular a bobina ao produto errado, então
    o auto-resolve deixa `material_version_id` NULL, igual à migração 0035.
    """
    for nome in ("PLA Preto ACME v1", "PLA Preto ACME v2"):
        r = await auth_client.post("/materials", json={
            "material_type": "PLA", "name": nome,
            "manufacturer": "ACME", "color": "Preto",
            "density_g_cm3": "1.24", "price_per_kg_ref": "100",
        })
        assert r.status_code == 201, r.text

    r = await auth_client.post("/spools", json={
        "material_type": "PLA", "manufacturer": "ACME", "color": "Preto",
        "purchased_at": "2026-06-01T00:00:00Z",
        "purchased_price": "100", "initial_grams": "1000", "remaining_grams": "1000",
    })
    assert r.status_code == 201, r.text
    assert r.json()["material_version_id"] is None


@pytest.mark.asyncio
async def test_spool_com_material_version_id_explicito_nao_e_sobrescrito(auth_client):
    """Um `material_version_id` explícito no POST manda, mesmo quando o
    trio (type/color/manufacturer) da bobina casaria com outro material via
    auto-resolve — enviado explicitamente nunca é sobrescrito.
    """
    r = await auth_client.post("/materials", json={
        "material_type": "PLA", "name": "PLA Preto Auto-resolveria",
        "manufacturer": "ACME", "color": "Preto",
        "density_g_cm3": "1.24", "price_per_kg_ref": "100",
    })
    assert r.status_code == 201, r.text
    mv_auto_id = r.json()["id"]

    r = await auth_client.post("/materials", json={
        "material_type": "PETG", "name": "PETG explícito",
        "manufacturer": "Voolt", "color": "Azul",
        "density_g_cm3": "1.27", "price_per_kg_ref": "150",
    })
    assert r.status_code == 201, r.text
    mv_explicito_id = r.json()["id"]

    r = await auth_client.post("/spools", json={
        "material_type": "PLA", "manufacturer": "ACME", "color": "Preto",
        "purchased_at": "2026-06-01T00:00:00Z",
        "purchased_price": "100", "initial_grams": "1000", "remaining_grams": "1000",
        "material_version_id": mv_explicito_id,
    })
    assert r.status_code == 201, r.text
    assert r.json()["material_version_id"] == mv_explicito_id
    assert r.json()["material_version_id"] != mv_auto_id
