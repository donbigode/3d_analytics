from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_ph = PasswordHasher(time_cost=2, memory_cost=65536)


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def make_jwt(sub: str, secret: str, ttl_days: int = 7) -> str:
    payload = {
        "sub": sub,
        "iat": datetime.now(tz=timezone.utc),
        "exp": datetime.now(tz=timezone.utc) + timedelta(days=ttl_days),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])


def validate_password_strength(password: str) -> None:
    """Politica mínima: 8+ chars, pelo menos 1 letra e 1 número.

    Levanta ``ValueError`` com mensagem em PT-BR quando inválida. Senha
    temporária ``F1odor_213`` passa (mix de letras + números, 10 chars).
    """
    if len(password) < 8:
        raise ValueError("senha precisa ter no mínimo 8 caracteres")
    if not any(c.isalpha() for c in password):
        raise ValueError("senha precisa ter pelo menos uma letra")
    if not any(c.isdigit() for c in password):
        raise ValueError("senha precisa ter pelo menos um número")
