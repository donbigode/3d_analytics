import pytest
import sqlalchemy as sa

from backend.core.models import QuoteKind, QuoteStatus
from backend.infra.db import session as session_module
from backend.infra.db.models import Person, Quote, User


async def _person(name):
    async with session_module.SessionFactory() as s:
        p = Person(name=name)
        s.add(p); await s.commit()
        return str(p.id)


async def _quote(kind, status):
    async with session_module.SessionFactory() as s:
        u = (await s.execute(sa.select(User))).scalars().first()
        q = Quote(kind=kind, user_id=u.id, status=status)
        s.add(q); await s.commit()
        return str(q.id)


@pytest.mark.asyncio
async def test_set_people_on_finished_personal_quote(auth_client):
    pid1 = await _person("Otávio")
    pid2 = await _person("Ana")
    qid = await _quote(QuoteKind.PERSONAL.value, QuoteStatus.ENTREGUE.value)  # finalizado

    r = await auth_client.put(f"/quotes/{qid}/people", json={"person_ids": [pid1, pid2]})
    assert r.status_code == 200, r.text
    assert set(r.json()["person_ids"]) == {pid1, pid2}

    # reescreve (só um agora)
    r = await auth_client.put(f"/quotes/{qid}/people", json={"person_ids": [pid1]})
    assert r.json()["person_ids"] == [pid1]

    # persiste no GET
    assert (await auth_client.get(f"/quotes/{qid}")).json()["person_ids"] == [pid1]


@pytest.mark.asyncio
async def test_people_rejected_on_commercial(auth_client):
    pid = await _person("Otávio")
    qid = await _quote(QuoteKind.COMMERCIAL.value, QuoteStatus.DRAFT.value)
    r = await auth_client.put(f"/quotes/{qid}/people", json={"person_ids": [pid]})
    assert r.status_code == 400, r.text
