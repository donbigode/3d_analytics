from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from backend.core.insights.personal_projects import compute_personal_projects
from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import (
    MaterialConsumption, Person, Quote, QuoteItem, QuotePerson, Spool, User,
)


@pytest.mark.asyncio
async def test_counts_grams_and_shared():
    async with session_module.SessionFactory() as s:
        u = User(name="u", email="pp@t.com", password_hash="x")
        s.add(u); await s.commit()
        otavio = Person(name="Otávio"); ana = Person(name="Ana")
        s.add_all([otavio, ana]); await s.commit()

        # projeto só do Otávio, com 100g de material
        q1 = Quote(kind=QuoteKind.PERSONAL.value, user_id=u.id, status=QuoteStatus.PRODUZIDO.value)
        # projeto compartilhado (Otávio + Ana)
        q2 = Quote(kind=QuoteKind.PERSONAL.value, user_id=u.id, status=QuoteStatus.PRODUZIDO.value)
        s.add_all([q1, q2]); await s.commit()
        s.add_all([
            QuotePerson(quote_id=q1.id, person_id=otavio.id),
            QuotePerson(quote_id=q2.id, person_id=otavio.id),
            QuotePerson(quote_id=q2.id, person_id=ana.id),
        ])
        item = QuoteItem(quote_id=q1.id, name="p", gcode_meta={}, quantity=1)
        spool = Spool(material_type="PLA", purchased_at=date(2026, 6, 1),
                      purchased_price=Decimal("100"), initial_grams=Decimal("1000"),
                      remaining_grams=Decimal("900"))
        s.add_all([item, spool]); await s.commit()
        s.add(MaterialConsumption(quote_item_id=item.id, spool_id=spool.id,
                                  grams_used=Decimal("100"), unit_cost_snapshot=Decimal("0.50"),
                                  consumed_at=datetime(2026, 6, 12, tzinfo=timezone.utc)))
        await s.commit()

    async with session_module.SessionFactory() as s:
        res = await compute_personal_projects(s, date(2026, 1, 1), date(2026, 12, 31))

    by_name = {p["name"]: p for p in res["people"]}
    assert by_name["Otávio"]["count"] == 2          # q1 + q2 (compartilhado conta)
    assert by_name["Ana"]["count"] == 1
    assert by_name["Otávio"]["grams"] == Decimal("100.00")
    assert res["shared_count"] == 1
