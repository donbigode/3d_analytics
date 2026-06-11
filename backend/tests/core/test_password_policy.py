import pytest
from backend.core.security import validate_password_strength


def test_accepts_strong_password():
    validate_password_strength("F1odor_213")  # 10 chars com mix


def test_rejects_too_short():
    with pytest.raises(ValueError, match="mínimo 8"):
        validate_password_strength("abc12")


def test_rejects_only_letters():
    with pytest.raises(ValueError, match="número"):
        validate_password_strength("abcdefghij")


def test_rejects_only_digits():
    with pytest.raises(ValueError, match="letra"):
        validate_password_strength("1234567890")
