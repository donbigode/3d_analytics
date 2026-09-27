import pytest


@pytest.mark.asyncio
async def test_material_put_creates_new_version(auth_client):
    r = await auth_client.post(
        "/materials",
        json={
            "material_type": "PLA",
            "name": "PLA Voolt Preto",
            "manufacturer": "Voolt",
            "color": "Preto",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "110",
            "failure_rate_pct": "5",
        },
    )
    assert r.status_code == 201
    v1 = r.json()
    assert v1["manufacturer"] == "Voolt"
    assert v1["color"] == "Preto"

    r = await auth_client.put(f"/materials/{v1['id']}", json={"price_per_kg_ref": "120"})
    assert r.status_code == 200
    v2 = r.json()
    assert v2["id"] != v1["id"]
    assert v2["price_per_kg_ref"] == "120.00"
    # carries over manufacturer + color
    assert v2["manufacturer"] == "Voolt"
    assert v2["color"] == "Preto"

    r = await auth_client.get(f"/materials/{v2['id']}/history")
    history = r.json()
    assert len(history) == 2
    assert sum(1 for v in history if v["is_current"]) == 1


@pytest.mark.asyncio
async def test_material_delete_only_if_unused(auth_client):
    r = await auth_client.post(
        "/materials",
        json={
            "material_type": "ABS",
            "name": "ABS",
            "density_g_cm3": "1.04",
            "price_per_kg_ref": "120",
            "failure_rate_pct": "10",
        },
    )
    mat_id = r.json()["id"]
    r = await auth_client.delete(f"/materials/{mat_id}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_material_usado_so_como_cor_2_bloqueia_delete_com_409(auth_client):
    """Um material referenciado só como linha 2+ (nunca linha 1) não aparece
    em `QuoteItem.material_version_id` — só em `QuoteItemFilament`. Sem
    checar essa tabela também, o hard-delete seguia e estourava violação de
    FK (500, `quote_item_filaments.material_version_id` é NOT NULL sem
    cascade) em vez do 409 que este endpoint promete.
    """
    from decimal import Decimal
    from uuid import UUID

    import sqlalchemy as sa

    from backend.core.models import QuoteKind, QuoteStatus
    from backend.infra.db import session as session_module
    from backend.infra.db.models import Quote, QuoteItem, QuoteItemFilament, User

    r1 = await auth_client.post("/materials", json={
        "material_type": "PLA", "name": "PLA Preto", "color": "Preto",
        "density_g_cm3": "1.24", "price_per_kg_ref": "100", "failure_rate_pct": "0",
    })
    mv_a_id = UUID(r1.json()["id"])
    r2 = await auth_client.post("/materials", json={
        "material_type": "PLA", "name": "PLA Dourado", "color": "Dourado",
        "density_g_cm3": "1.24", "price_per_kg_ref": "250", "failure_rate_pct": "0",
    })
    mv_b_id = UUID(r2.json()["id"])

    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=u.id,
                  status=QuoteStatus.DRAFT.value, markup_pct=Decimal("0"),
                  min_charge=Decimal("0"))
        s.add(q)
        await s.commit()
        it = QuoteItem(quote_id=q.id, name="bicolor",
                       gcode_meta={"filament_m": 10, "time_s": 3600},
                       material_version_id=mv_a_id, quantity=1, is_multi_color=True)
        s.add(it)
        await s.commit()
        s.add_all([
            QuoteItemFilament(quote_item_id=it.id, material_version_id=mv_a_id,
                              grams_unit=Decimal("10"), position=1),
            QuoteItemFilament(quote_item_id=it.id, material_version_id=mv_b_id,
                              grams_unit=Decimal("5"), position=2),
        ])
        await s.commit()

    r = await auth_client.delete(f"/materials/{mv_b_id}")
    assert r.status_code == 409, (
        f"esperava 409 (material em uso só como linha 2+), veio {r.status_code}: {r.text}"
    )


@pytest.mark.asyncio
async def test_multiple_materials_same_type(auth_client):
    """Two PLAs from different manufacturers are independently tracked."""
    r1 = await auth_client.post(
        "/materials",
        json={
            "material_type": "PLA",
            "name": "PLA Voolt Preto",
            "manufacturer": "Voolt",
            "color": "Preto",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "110",
            "failure_rate_pct": "5",
        },
    )
    r2 = await auth_client.post(
        "/materials",
        json={
            "material_type": "PLA",
            "name": "PLA Esun Branco",
            "manufacturer": "Esun",
            "color": "Branco",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "95",
            "failure_rate_pct": "5",
        },
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    listing = (await auth_client.get("/materials")).json()
    plas = [m for m in listing if m["material_type"] == "PLA"]
    assert len(plas) == 2
