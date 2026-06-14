import pytest

from backend.tests.api.test_production_flow import (
    _approved_commercial,
    _seed_material,
    _spool,
)


@pytest.mark.asyncio
async def test_failure_rates_by_material(auth_client):
    await _seed_material(auth_client)
    sid = await _spool(auth_client)
    # 1 falha
    qid, item_id = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid}/transitions/produce",
        json={"consumption": [{"quote_item_id": item_id, "spool_id": sid}]})
    await auth_client.post(f"/quotes/{qid}/transitions/fail",
        json={"failure_description": "warping", "attempts": 1})
    # 1 sucesso
    qid2, item2 = await _approved_commercial(auth_client)
    await auth_client.post(f"/quotes/{qid2}/transitions/produce",
        json={"consumption": [{"quote_item_id": item2, "spool_id": sid}]})
    await auth_client.post(f"/quotes/{qid2}/transitions/complete", json={"attempts": 1})

    r = await auth_client.get("/insights/failure-rates")
    assert r.status_code == 200, r.text
    rows = r.json()["by_material"]
    pla = next(x for x in rows if x["material_type"] == "PLA")
    assert pla["failures"] == 1
    assert pla["total"] == 2
    assert 0.49 <= float(pla["failure_rate"]) <= 0.51
