import argparse
import asyncio

from backend.core.security import hash_password
from backend.infra.db.session import SessionFactory
from backend.infra.db.models import User


async def _create_user(name: str, email: str, password: str):
    async with SessionFactory() as s:
        u = User(name=name, email=email, password_hash=hash_password(password))
        s.add(u); await s.commit()
        print(f"created user {u.id}")


def main() -> None:
    p = argparse.ArgumentParser(prog="3d-analytics")
    sub = p.add_subparsers(dest="cmd", required=True)
    cu = sub.add_parser("create-user")
    cu.add_argument("--name", required=True)
    cu.add_argument("--email", required=True)
    cu.add_argument("--password", required=True)
    sub.add_parser("seed")
    sub.add_parser("version")
    args = p.parse_args()
    if args.cmd == "create-user":
        asyncio.run(_create_user(args.name, args.email, args.password))
    elif args.cmd == "version":
        print("0.1.0")
    elif args.cmd == "seed":
        print("seed not implemented yet")


if __name__ == "__main__":
    main()
