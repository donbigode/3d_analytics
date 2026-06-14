import pytest


@pytest.mark.asyncio
async def test_fill_failure_embeddings_sets_vectors(auth_client, monkeypatch):
    from sqlalchemy import select

    from backend.core.production import suggestions as S
    from backend.infra.db.models import ProductionEvent
    from backend.infra.db.session import SessionFactory
    from backend.tests.api.test_production_flow import (
        _approved_commercial,
        _seed_material,
        _spool,
    )

    async def fake_embed(texts):
        return [[0.1] * 384 for _ in texts]

    monkeypatch.setattr(S, "embed", fake_embed)

    await _seed_material(auth_client)
    sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    await auth_client.post(f"/quotes/{qid}/transitions/fail",
        json={"failure_description": "warping", "attempts": 1})

    async with SessionFactory() as session:
        # A suíte compartilha o DB, então pode haver outras falhas pendentes;
        # garantimos pelo menos a nossa e checamos o vetor dela.
        n = await S.fill_failure_embeddings(session)
        assert n >= 1
        import uuid as _uuid
        ev = (await session.execute(
            select(ProductionEvent).where(
                ProductionEvent.outcome == "failure",
                ProductionEvent.quote_id == _uuid.UUID(qid),
            )
        )).scalars().first()
        assert ev is not None
        assert ev.embedding is not None
        assert len(list(ev.embedding)) == 384


@pytest.mark.asyncio
async def test_generate_suggestions_caches_llm_output(auth_client, monkeypatch):
    from sqlalchemy import select

    from backend.core.production import suggestions as S
    from backend.infra.db.models import ProductionSuggestion
    from backend.infra.db.session import SessionFactory
    from backend.tests.api.test_production_flow import (
        _approved_commercial,
        _seed_material,
        _spool,
    )

    async def fake_embed(texts):
        return [[0.1] * 384 for _ in texts]

    async def fake_call_json(session, *, system, user, max_tokens=800):
        return {"suggestions": [
            {"material_type": "PLA", "advice": "reduza velocidade da 1a camada"}
        ]}

    monkeypatch.setattr(S, "embed", fake_embed)
    monkeypatch.setattr(S, "call_json", fake_call_json)

    await _seed_material(auth_client)
    sid = await _spool(auth_client)
    qid, item_id = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    await auth_client.post(f"/quotes/{qid}/transitions/fail",
        json={"failure_description": "warping nos cantos", "attempts": 1})

    async with SessionFactory() as session:
        out = await S.generate_suggestions(session)
        assert out["source_count"] == 1
        assert out["suggestions"][0]["material_type"] == "PLA"
        cached = (await session.execute(select(ProductionSuggestion))).scalars().all()
        assert len(cached) == 1


@pytest.mark.asyncio
async def test_suggestions_endpoints_generate_and_read(auth_client, monkeypatch):
    import backend.api.routes.insights as I

    async def fake_generate(session):
        return {"suggestions": [{"material_type": "PLA", "advice": "x"}],
                "source_count": 1, "provider": "llm"}
    monkeypatch.setattr(I, "generate_suggestions", fake_generate)

    # GET sempre responde 200 com a forma esperada (lista de sugestões).
    r0 = await auth_client.get("/insights/production-suggestions")
    assert r0.status_code == 200, r0.text
    assert isinstance(r0.json()["suggestions"], list)
    assert "stale" in r0.json()

    # POST usa o gerador (stub) e devolve o payload dele.
    r = await auth_client.post("/insights/production-suggestions/generate")
    assert r.status_code == 200, r.text
    assert r.json()["suggestions"][0]["material_type"] == "PLA"


@pytest.mark.asyncio
async def test_production_suggestion_table_exists(auth_client):
    from backend.infra.db.models import ProductionSuggestion
    assert ProductionSuggestion.__tablename__ == "production_suggestions"
    cols = set(ProductionSuggestion.__table__.columns.keys())
    assert {"id", "body", "provider", "source_count", "generated_at"} <= cols
