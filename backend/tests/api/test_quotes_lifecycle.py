import pytest
from decimal import Decimal


GCODE_SAMPLE = b";TIME:3600\n;Filament used:5.0m\n;Material Type:PLA\n;Machine Name:K2\n"


async def _seed_material(client):
    await client.post(
        "/materials",
        json={
            "material_type": "PLA",
            "name": "PLA",
            "density_g_cm3": "1.24",
            "price_per_kg_ref": "100",
            "failure_rate_pct": "0",
        },
    )


@pytest.mark.asyncio
async def test_reopen_quote_from_orcado_back_to_draft(auth_client):
    """The cliente asked for one more part after the quote was finalized;
    reopen lets the owner add it without losing history. Only allowed from
    'orcado' and only for commercial quotes."""
    await _seed_material(auth_client)
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("p.gcode", GCODE_SAMPLE, "application/octet-stream")}
    await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "A", "quantity": "1"}
    )
    r = await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    assert r.json()["status"] == "orcado"

    # Reopen — back to draft.
    r = await auth_client.post(f"/quotes/{qid}/transitions/reopen")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["finalized_at"] is None  # cleared so refinalize stamps fresh

    # Now we can add a new item.
    files2 = {"file": ("p2.gcode", GCODE_SAMPLE, "application/octet-stream")}
    r = await auth_client.post(
        f"/quotes/{qid}/items", files=files2, data={"name": "B", "quantity": "2"}
    )
    assert r.status_code == 201
    assert len(r.json()["items"]) == 2

    # Reopening from non-orcado states is rejected.
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    await auth_client.post(f"/quotes/{qid}/transitions/approve")
    r = await auth_client.post(f"/quotes/{qid}/transitions/reopen")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_reopen_rejects_personal(auth_client):
    await _seed_material(auth_client)
    r = await auth_client.post("/quotes", json={"kind": "personal"})
    qid = r.json()["id"]
    r = await auth_client.post(f"/quotes/{qid}/transitions/reopen")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_add_item_without_file(auth_client):
    """Items can be added without a gcode — tempo/filamento entered manually
    via the inline editors later. Reparse must refuse on these items."""
    await _seed_material(auth_client)
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    # No file in the multipart body — just name + quantity.
    r = await auth_client.post(
        f"/quotes/{qid}/items",
        data={"name": "porta-caneta manual", "quantity": "2"},
    )
    assert r.status_code == 201, r.text
    item = r.json()["items"][0]
    assert item["name"] == "porta-caneta manual"
    assert item["filename"] is None
    # Manual fill then check cost recomputes once material is set.
    r = await auth_client.put(
        f"/quotes/{qid}/items/{item['id']}",
        json={"time_s": 3600, "filament_m": 5.0},
    )
    assert r.status_code == 200
    # Reparse on an item with no file → 409 with a clear message.
    r = await auth_client.post(f"/quotes/{qid}/items/{item['id']}/reparse")
    assert r.status_code == 409
    assert "gcode" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reparse_item_runs_parser_on_stored_file(auth_client):
    """The reparse endpoint reads the gcode file from disk and refreshes
    gcode_meta. We poison the meta with zeros, then verify reparse restores
    the parser's output from the stored file."""
    await _seed_material(auth_client)
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("part.gcode", GCODE_SAMPLE, "application/octet-stream")}
    r = await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "Peca X", "quantity": "1"}
    )
    item_id = r.json()["items"][0]["id"]

    r = await auth_client.put(
        f"/quotes/{qid}/items/{item_id}",
        json={"time_s": 0, "filament_m": 0},
    )
    assert r.status_code == 200
    assert r.json()["items"][0]["gcode_meta"]["time_s"] == 0

    r = await auth_client.post(f"/quotes/{qid}/items/{item_id}/reparse")
    assert r.status_code == 200, r.text
    meta = r.json()["items"][0]["gcode_meta"]
    assert meta["time_s"] == 3600
    assert meta["filament_m"] == 5.0


@pytest.mark.asyncio
async def test_commercial_lifecycle(auth_client):
    await _seed_material(auth_client)

    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    assert r.status_code == 201, r.text
    qid = r.json()["id"]
    assert r.json()["status"] == "draft"

    files = {"file": ("test.gcode", GCODE_SAMPLE, "application/octet-stream")}
    r = await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "Peca A", "quantity": "1"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Peca A"

    r = await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "orcado"
    assert r.json()["finalized_at"] is not None

    r = await auth_client.post(f"/quotes/{qid}/transitions/approve")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "aprovado"


@pytest.mark.asyncio
async def test_produce_consumes_spool(auth_client):
    await _seed_material(auth_client)

    r = await auth_client.post(
        "/spools",
        json={
            "material_type": "PLA",
            "purchased_at": "2026-06-01T00:00:00Z",
            "purchased_price": "100",
            "initial_grams": "1000",
            "remaining_grams": "1000",
        },
    )
    assert r.status_code == 201, r.text
    spool_id = r.json()["id"]

    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("x.gcode", GCODE_SAMPLE, "application/octet-stream")}
    await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "X", "quantity": "1"}
    )
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    await auth_client.post(f"/quotes/{qid}/transitions/approve")

    quote = (await auth_client.get(f"/quotes/{qid}")).json()
    item_id = quote["items"][0]["id"]

    r = await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": spool_id}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "produzido"

    s = (await auth_client.get(f"/spools/{spool_id}")).json()
    assert Decimal(s["remaining_grams"]) < Decimal("1000")


@pytest.mark.asyncio
async def test_produce_insufficient_spool_returns_409(auth_client):
    await _seed_material(auth_client)
    r = await auth_client.post(
        "/spools",
        json={
            "material_type": "PLA",
            "purchased_at": "2026-06-01T00:00:00Z",
            "purchased_price": "100",
            "initial_grams": "1",
            "remaining_grams": "1",
        },
    )
    spool_id = r.json()["id"]

    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("x.gcode", GCODE_SAMPLE, "application/octet-stream")}
    await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "X", "quantity": "1"}
    )
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    await auth_client.post(f"/quotes/{qid}/transitions/approve")
    quote = (await auth_client.get(f"/quotes/{qid}")).json()
    item_id = quote["items"][0]["id"]

    r = await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": spool_id}]},
    )
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_produce_rejects_item_without_filament(auth_client):
    """An item whose gcode has no filament length would silently debit 0g.
    Producing it must fail loudly instead of creating a no-op consumption."""
    await _seed_material(auth_client)
    r = await auth_client.post(
        "/spools",
        json={
            "material_type": "PLA",
            "purchased_at": "2026-06-01T00:00:00Z",
            "purchased_price": "100",
            "initial_grams": "1000",
            "remaining_grams": "1000",
        },
    )
    spool_id = r.json()["id"]

    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    no_filament = b";TIME:3600\n;Filament used:0m\n;Material Type:PLA\n"
    files = {"file": ("x.gcode", no_filament, "application/octet-stream")}
    await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "X", "quantity": "1"}
    )
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    await auth_client.post(f"/quotes/{qid}/transitions/approve")
    quote = (await auth_client.get(f"/quotes/{qid}")).json()
    item_id = quote["items"][0]["id"]

    r = await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": spool_id}]},
    )
    assert r.status_code == 409, r.text

    # spool untouched — the whole transaction must roll back
    s = (await auth_client.get(f"/spools/{spool_id}")).json()
    assert Decimal(s["remaining_grams"]) == Decimal("1000")


@pytest.mark.asyncio
async def test_commercial_can_deliver_after_produce(auth_client):
    await _seed_material(auth_client)
    r = await auth_client.post(
        "/spools",
        json={
            "material_type": "PLA",
            "purchased_at": "2026-06-01T00:00:00Z",
            "purchased_price": "100",
            "initial_grams": "1000",
            "remaining_grams": "1000",
        },
    )
    spool_id = r.json()["id"]
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("x.gcode", GCODE_SAMPLE, "application/octet-stream")}
    await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "X", "quantity": "1"}
    )
    await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    await auth_client.post(f"/quotes/{qid}/transitions/approve")
    quote = (await auth_client.get(f"/quotes/{qid}")).json()
    item_id = quote["items"][0]["id"]
    await auth_client.post(
        f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": spool_id}]},
    )
    r = await auth_client.post(f"/quotes/{qid}/transitions/deliver")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "entregue"


@pytest.mark.asyncio
async def test_upload_unknown_material_creates_pending_item(auth_client):
    # No material seeded — item is accepted as pending; finalize is blocked
    # until material is registered and item resolved.
    r = await auth_client.post("/quotes", json={"kind": "commercial"})
    qid = r.json()["id"]
    files = {"file": ("x.gcode", GCODE_SAMPLE, "application/octet-stream")}
    r = await auth_client.post(
        f"/quotes/{qid}/items", files=files, data={"name": "X", "quantity": "1"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["pending_items"] == 1
    item = body["items"][0]
    assert item["material_pending"] is True
    assert item["pending_material_code"] == "PLA"
    # finalize must be blocked
    r = await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    assert r.status_code == 409
    # register material and resolve item
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
    item_id = item["id"]
    r = await auth_client.put(
        f"/quotes/{qid}/items/{item_id}", json={"material_code": "PLA"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["material_pending"] is False
    assert r.json()["pending_items"] == 0
    # now finalize succeeds
    r = await auth_client.post(f"/quotes/{qid}/transitions/finalize")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "orcado"
