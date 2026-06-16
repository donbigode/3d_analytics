from datetime import date
from decimal import Decimal
import pytest
from backend.core.accounting.profitability import compute_profitability
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    Client, MaterialVersion, Quote, QuoteItem, Sale, User,
)


@pytest.mark.asyncio
async def test_profitability_by_client_and_material():
    async with session_module.SessionFactory() as s:
        user = User(name="u", email="prof@t.com", password_hash="x")
        cli = Client(name="Ana")
        mv = MaterialVersion(material_type="PLA", name="PLA", density_g_cm3=Decimal("1.24"),
                             price_per_kg_ref=Decimal("100"))
        s.add_all([user, cli, mv]); await s.commit()
        q = Quote(kind=QuoteKind.COMMERCIAL.value, user_id=user.id, client_id=cli.id,
                  status=QuoteStatus.ENTREGUE.value, markup_pct=Decimal("0"), min_charge=Decimal("0"))
        s.add(q); await s.commit()
        s.add(QuoteItem(quote_id=q.id, name="p", gcode_meta={"filament_m": 10},
                        material_version_id=mv.id, quantity=1))
        s.add(Sale(quote_id=q.id, quote_status="entregue", quote_kind="commercial",
                   quote_total=Decimal("200"), cpv_calc=Decimal("50"), is_sold=True, is_stale=False,
                   confirmed_revenue=Decimal("200"), variable_costs=Decimal("0"),
                   client_id=cli.id, sold_at=date(2026, 6, 10)))
        await s.commit()

    async with session_module.SessionFactory() as s:
        prof = await compute_profitability(s, date(2026, 6, 1), date(2026, 6, 30))

    by_client = {r["label"]: r for r in prof["by_client"]}
    assert by_client["Ana"]["receita"] == Decimal("200.00")
    assert by_client["Ana"]["margem"] == Decimal("150.00")
    by_mat = {r["label"]: r for r in prof["by_material"]}
    assert by_mat["PLA"]["receita"] == Decimal("200.00")
    assert by_mat["PLA"]["margem"] == Decimal("150.00")
