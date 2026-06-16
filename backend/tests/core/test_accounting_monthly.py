from datetime import date
import pytest
from backend.core.accounting.monthly import compute_dre_monthly
from backend.infra.db import session as session_module


@pytest.mark.asyncio
async def test_monthly_returns_one_per_month():
    async with session_module.SessionFactory() as s:
        rows = await compute_dre_monthly(s, date(2026, 1, 1), date(2026, 3, 31))
    assert [r["month"] for r in rows] == ["2026-01", "2026-02", "2026-03"]
    for r in rows:
        assert "resultado_liquido" in r
