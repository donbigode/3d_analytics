import io
import pytest


@pytest.mark.asyncio
async def test_settings_get_and_update(auth_client):
    r = await auth_client.get("/settings")
    assert r.status_code == 200
    data = r.json()
    assert "currency" in data

    r = await auth_client.put("/settings", json={"currency": "USD", "business_name": "Acme"})
    assert r.status_code == 200
    assert r.json()["currency"] == "USD"
    assert r.json()["business_name"] == "Acme"


@pytest.mark.asyncio
async def test_settings_logo_upload(auth_client, tmp_path, monkeypatch):
    # Redirect storage to tmp_path so we don't pollute /data/storage
    from backend.settings import AppSettings, get_settings  # noqa: F401
    from backend import settings as settings_mod
    monkeypatch.setattr(settings_mod, "get_settings",
                        lambda: AppSettings(storage_dir=str(tmp_path)))
    # The branding module imports get_settings via its own module — patch that too
    from backend.infra.storage import branding as branding_mod
    monkeypatch.setattr(branding_mod, "get_settings",
                        lambda: AppSettings(storage_dir=str(tmp_path)))

    files = {"file": ("logo.png", io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\0" * 16), "image/png")}
    r = await auth_client.post("/settings/logo", files=files)
    assert r.status_code == 200, r.text
    assert r.json()["logo_path"] == "branding/logo.png"
    assert (tmp_path / "branding" / "logo.png").exists()


@pytest.mark.asyncio
async def test_settings_revenue_tax(auth_client):
    r = await auth_client.put("/settings", json={"revenue_tax_pct": "6.00"})
    assert r.status_code == 200, r.text
    assert r.json()["revenue_tax_pct"] == "6.00"


@pytest.mark.asyncio
async def test_settings_logo_rejects_bad_extension(auth_client, tmp_path, monkeypatch):
    from backend.settings import AppSettings
    from backend.infra.storage import branding as branding_mod
    monkeypatch.setattr(branding_mod, "get_settings",
                        lambda: AppSettings(storage_dir=str(tmp_path)))

    files = {"file": ("logo.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
    r = await auth_client.post("/settings/logo", files=files)
    assert r.status_code == 400
