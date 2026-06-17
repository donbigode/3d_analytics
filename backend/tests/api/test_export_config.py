import pytest


@pytest.mark.asyncio
async def test_export_config_get_put_mask(auth_client):
    # default
    r = await auth_client.get("/config/export")
    assert r.status_code == 200, r.text
    # configura s3 com segredo
    r = await auth_client.put("/config/export", json={
        "destination": "s3", "s3_bucket": "meu-bucket", "s3_region": "us-east-1",
        "s3_access_key_id": "AKIA", "s3_secret_access_key": "supersecret", "enabled": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["destination"] == "s3"
    assert body["s3_bucket"] == "meu-bucket"
    assert body["enabled"] is True
    # segredo mascarado (não retorna o valor cru)
    assert body["s3_secret_access_key_preview"] != "supersecret"
    assert body["s3_secret_configured"] is True


@pytest.mark.asyncio
async def test_export_run_force(auth_client, monkeypatch):
    import backend.api.routes.config as cfg_routes

    async def fake_execute(session):
        return {"ok": True, "run_ts": "20260617T000000Z", "counts": {"quotes": 0}}
    monkeypatch.setattr(cfg_routes, "execute_export", fake_execute)

    r = await auth_client.post("/config/export/run")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
