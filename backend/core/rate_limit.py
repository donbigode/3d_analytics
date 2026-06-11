"""Rate limiting no FastAPI usando slowapi.

Limites:
  - /auth/login: 10 req/min/IP (anti-brute-force)
  - Resto: sem limite global (a aplicação é interna, só 2 usuários)

Quando o limite estoura, devolve 429 Too Many Requests com o JSON
``{"detail": "rate limit excedido, aguarde"}``.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi import Request
from fastapi.responses import JSONResponse


def _key(request: Request) -> str:
    return get_remote_address(request) or "test"


limiter = Limiter(key_func=_key)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "rate limit excedido, aguarde alguns segundos"},
    )
