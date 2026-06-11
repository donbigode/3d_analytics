import pytest


@pytest.mark.asyncio
async def test_login_rate_limit(client):
    """11th attempt within <1min should return 429."""
    for _ in range(10):
        r = await client.post(
            "/auth/login",
            json={"email": "nope@nope.com", "password": "x"},
        )
        assert r.status_code == 401, r.text
    # The 11th attempt:
    r = await client.post(
        "/auth/login",
        json={"email": "nope@nope.com", "password": "x"},
    )
    assert r.status_code == 429
    assert "rate limit" in r.json()["detail"].lower()
