import pytest


@pytest.mark.asyncio
async def test_change_password_happy_path(auth_client):
    r = await auth_client.post(
        "/auth/change-password",
        json={"current_password": "pw", "new_password": "Nova_S3nha!"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    # next login must use the new password
    r = await auth_client.post(
        "/auth/logout"
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_change_password_wrong_current(auth_client):
    r = await auth_client.post(
        "/auth/change-password",
        json={"current_password": "wrong", "new_password": "Nova_S3nha!"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_change_password_rejects_weak(auth_client):
    r = await auth_client.post(
        "/auth/change-password",
        json={"current_password": "pw", "new_password": "short"},
    )
    assert r.status_code == 400
    assert "mínimo 8" in r.json()["detail"]
