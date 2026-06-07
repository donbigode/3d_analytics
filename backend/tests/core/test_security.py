from backend.core.security import hash_password, verify_password, make_jwt, decode_jwt


def test_hash_verifies():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_jwt_roundtrip():
    token = make_jwt(sub="user-id-123", secret="x" * 32)
    claims = decode_jwt(token, secret="x" * 32)
    assert claims["sub"] == "user-id-123"
