"""Dependencies: container access, authentication, authorization, pagination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Query, Request
from sqlalchemy import select

from forgeflow.api.errors import APIError
from forgeflow.container import Container
from forgeflow.db.models import AuditLog, User
from forgeflow.security.auth import Role, hash_token
from forgeflow.security.redaction import redact_obj


def get_container(request: Request) -> Container:
    return request.app.state.container  # type: ignore[no-any-return]


ContainerDep = Annotated[Container, Depends(get_container)]


@dataclass
class Principal:
    id: str
    name: str
    role: Role

    @property
    def actor(self) -> str:
        return f"{self.name} ({self.id})"


async def get_principal(
    c: ContainerDep, request: Request, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise APIError(401, "unauthorized", "Missing bearer token")
    token = authorization[7:].strip()
    async with c.services.db.session() as s:
        user = await s.scalar(select(User).where(User.token_hash == hash_token(token)))
    if user is None:
        raise APIError(401, "unauthorized", "Invalid token")
    principal = Principal(id=user.id, name=user.name, role=Role[user.role])
    limiter = request.app.state.rate_limiter
    if not await limiter.hit(f"user:{user.id}"):
        raise APIError(429, "rate_limited", "Rate limit exceeded")
    return principal


def require(role: Role):  # type: ignore[no-untyped-def]
    async def dep(p: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if p.role < role:
            raise APIError(403, "forbidden", f"Requires {role.name} role")
        return p

    return dep


Viewer = Annotated[Principal, Depends(require(Role.viewer))]
Operator = Annotated[Principal, Depends(require(Role.operator))]
Admin = Annotated[Principal, Depends(require(Role.admin))]


@dataclass
class Pagination:
    limit: int
    offset: int


def pagination(limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0) -> Pagination:
    return Pagination(limit=limit, offset=offset)


PageDep = Annotated[Pagination, Depends(pagination)]


async def audit(c: Container, actor: str, action: str, target: str | None = None, **details: object) -> None:
    async with c.services.db.session() as s:
        s.add(AuditLog(actor=actor, action=action, target=target, details=redact_obj(details)))
