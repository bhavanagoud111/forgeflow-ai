"""Administrative CLI: ``uv run forgeflow create-token --name alice --role operator``."""

from __future__ import annotations

import argparse
import asyncio

from forgeflow.config import get_settings
from forgeflow.container import build_container, ensure_user
from forgeflow.security.auth import new_token


async def _create_token(name: str, role: str) -> str:
    c = await build_container(get_settings())
    try:
        token = new_token()
        await ensure_user(c.services.db, name, role, token)
        return token
    finally:
        await c.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="forgeflow")
    sub = parser.add_subparsers(dest="command", required=True)
    tok = sub.add_parser("create-token", help="Create a user and print its API token (shown once)")
    tok.add_argument("--name", required=True)
    tok.add_argument("--role", choices=["viewer", "operator", "admin"], default="operator")
    args = parser.parse_args()
    if args.command == "create-token":
        print(asyncio.run(_create_token(args.name, args.role)))
