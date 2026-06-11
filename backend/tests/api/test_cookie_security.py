import pytest


@pytest.mark.asyncio
async def test_login_sets_lax_cookie_in_dev_by_default(auth_client):
    """ENV unset/dev: cookie should be HttpOnly + SameSite=Lax, NO Secure.

    The auth_client fixture is already logged in; here we re-login through
    the public endpoint with the same creds and inspect the Set-Cookie
    header that comes back.
    """
    # The conftest creates a user with email t@t.com and password 'pw'
    # via the test client; re-login here to capture cookie attributes.
    r = await auth_client.post(
        "/auth/login",
        json={"email": "t@t.com", "password": "pw"},
    )
    assert r.status_code == 200, r.text
    set_cookie = r.headers.get("set-cookie", "")
    assert "session=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    assert "secure" not in set_cookie.lower(), set_cookie
