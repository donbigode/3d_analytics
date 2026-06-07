"""Provider config endpoint — set, mask, clear, toggle."""
import pytest


@pytest.mark.asyncio
async def test_providers_get_default_state(auth_client):
    r = await auth_client.get("/config/providers")
    assert r.status_code == 200
    body = r.json()
    assert body["preferred_llm_provider"] == "anthropic"
    assert body["llm_suggestions_enabled"] is False
    assert body["anthropic_configured"] is False
    assert body["anthropic_key_preview"] is None
    assert body["gemini_configured"] is False


@pytest.mark.asyncio
async def test_providers_set_anthropic_masks_value(auth_client):
    r = await auth_client.put(
        "/config/providers",
        json={"anthropic_api_key": "sk-ant-abc-1234567890xyz"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["anthropic_configured"] is True
    # preview is masked head + tail
    assert body["anthropic_key_preview"].startswith("sk-a")
    assert body["anthropic_key_preview"].endswith("0xyz")
    assert "…" in body["anthropic_key_preview"]


@pytest.mark.asyncio
async def test_providers_clear_with_empty_string(auth_client):
    # First, set
    await auth_client.put("/config/providers", json={"gemini_api_key": "AIza-test-key-1234"})
    # Then, clear
    r = await auth_client.put("/config/providers", json={"gemini_api_key": ""})
    body = r.json()
    assert body["gemini_configured"] is False
    assert body["gemini_key_preview"] is None


@pytest.mark.asyncio
async def test_providers_toggle_enabled_and_preferred(auth_client):
    r = await auth_client.put(
        "/config/providers",
        json={
            "preferred_llm_provider": "gemini",
            "llm_suggestions_enabled": True,
        },
    )
    body = r.json()
    assert body["preferred_llm_provider"] == "gemini"
    assert body["llm_suggestions_enabled"] is True


@pytest.mark.asyncio
async def test_providers_invalid_preferred_returns_400(auth_client):
    r = await auth_client.put(
        "/config/providers",
        json={"preferred_llm_provider": "openai"},
    )
    assert r.status_code == 400
