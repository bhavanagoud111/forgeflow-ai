"""Bearer-token authentication and role-based authorization."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from enum import IntEnum


class Role(IntEnum):
    viewer = 1
    operator = 2
    admin = 3


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_match(token: str, token_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), token_hash)


def new_token() -> str:
    return "ffa_" + secrets.token_urlsafe(32)
