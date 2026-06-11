"""Provisiona os 2 usuários iniciais (Otavio + Ana) no primeiro boot.

Lê emails e senha das variáveis de ambiente:
  - SEED_USER_OTAVIO_EMAIL
  - SEED_USER_ANA_EMAIL
  - SEED_INITIAL_PASSWORD  (senha temporária, será trocada no 1º login)

Idempotente: se o email já existe, pula sem mudar nada. Usa Argon2id
via :func:`backend.core.security.hash_password`.

Uso:
  docker compose -f docker-compose.prod.yml run --rm api python -m backend.scripts.seed_users
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.security import hash_password
from backend.infra.db.models import User
from backend.infra.db.session import SessionFactory

logger = logging.getLogger(__name__)

# (name, env_var_email)
_SEED_TABLE: list[tuple[str, str]] = [
    ("Otavio Geraldo", "SEED_USER_OTAVIO_EMAIL"),
    ("Ana Clara Borges", "SEED_USER_ANA_EMAIL"),
]


async def run_seed(session: AsyncSession) -> int:
    """Cria os usuários que faltam. Retorna quantos foram inseridos."""
    password = os.environ.get("SEED_INITIAL_PASSWORD")
    if not password:
        raise RuntimeError("SEED_INITIAL_PASSWORD não definido")
    pw_hash = hash_password(password)
    created = 0
    for name, env_var in _SEED_TABLE:
        email = os.environ.get(env_var)
        if not email:
            logger.warning("pulando %s — variável %s não definida", name, env_var)
            continue
        existing = await session.scalar(
            select(User).where(User.email == email)
        )
        if existing:
            logger.info("usuário %s já existe — pulando", email)
            continue
        session.add(
            User(
                name=name,
                email=email,
                password_hash=pw_hash,
                must_change_password=True,
            )
        )
        created += 1
        logger.info("criando usuário %s", email)
    await session.commit()
    return created


async def _main() -> int:
    logging.basicConfig(level=logging.INFO)
    async with SessionFactory() as session:
        n = await run_seed(session)
    logger.info("seed concluído: %d usuário(s) inseridos", n)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
