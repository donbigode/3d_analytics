import pytest


@pytest.mark.asyncio
async def test_production_suggestion_table_exists(auth_client):
    from backend.infra.db.models import ProductionSuggestion
    assert ProductionSuggestion.__tablename__ == "production_suggestions"
    cols = set(ProductionSuggestion.__table__.columns.keys())
    assert {"id", "body", "provider", "source_count", "generated_at"} <= cols
