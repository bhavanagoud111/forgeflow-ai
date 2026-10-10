"""Repository and historical memory.

Repository memory holds the latest structural knowledge about a repository (architecture,
conventions, dependencies, tests). Historical memory records investigations, approved
fixes, failure patterns and decisions so later executions can reuse them. Everything is
redacted before storage, and both stores have retention / deletion paths.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from forgeflow.db.models import HistoricalMemory, RepositoryMemory, utcnow
from forgeflow.db.session import Database
from forgeflow.repository.indexer import tokenize
from forgeflow.security.redaction import redact, redact_obj

REPO_KINDS = ("architecture", "conventions", "dependencies", "test_structure", "modules")
HISTORY_KINDS = ("investigation", "approved_fix", "failure_pattern", "decision")


class MemoryStore:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def save_repository(self, repository_id: str, entries: dict[str, dict[str, Any]]) -> None:
        unknown = set(entries) - set(REPO_KINDS)
        if unknown:
            raise ValueError(f"unknown repository memory kind {sorted(unknown)}")
        # Atomic upsert: concurrent executions on the same repository may write at the same time.
        insert = pg_insert if self.db.url.startswith("postgres") else sqlite_insert
        async with self.db.session() as s:
            for kind, content in entries.items():
                stmt = insert(RepositoryMemory).values(
                    repository_id=repository_id, kind=kind, content=redact_obj(content), updated_at=utcnow()
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["repository_id", "kind"],
                    set_={"content": stmt.excluded.content, "updated_at": stmt.excluded.updated_at},
                )
                await s.execute(stmt)

    async def repository(self, repository_id: str) -> dict[str, dict[str, Any]]:
        async with self.db.session() as s:
            rows = await s.scalars(select(RepositoryMemory).where(RepositoryMemory.repository_id == repository_id))
            return {r.kind: r.content for r in rows}

    async def remember(
        self,
        repository_id: str,
        kind: str,
        title: str,
        content: str,
        *,
        execution_id: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        if kind not in HISTORY_KINDS:
            raise ValueError(f"unknown history kind {kind}")
        async with self.db.session() as s:
            s.add(
                HistoricalMemory(
                    repository_id=repository_id,
                    execution_id=execution_id,
                    kind=kind,
                    title=redact(title)[:300],
                    content=redact(content)[:8000],
                    tags=tags or [],
                )
            )

    async def recall(
        self, repository_id: str, query: str, k: int = 5, kinds: tuple[str, ...] = HISTORY_KINDS
    ) -> list[dict[str, Any]]:
        """Lexical recall over historical memory for this repository."""
        q = set(tokenize(query))
        async with self.db.session() as s:
            rows = list(
                await s.scalars(
                    select(HistoricalMemory)
                    .where(HistoricalMemory.repository_id == repository_id, HistoricalMemory.kind.in_(kinds))
                    .order_by(HistoricalMemory.created_at.desc())
                    .limit(500)
                )
            )
        scored = []
        for r in rows:
            words = set(tokenize(f"{r.title} {r.content} {' '.join(r.tags)}"))
            overlap = len(q & words)
            if overlap:
                scored.append((overlap, r))
        scored.sort(key=lambda x: -x[0])
        return [
            {
                "kind": r.kind,
                "title": r.title,
                "content": r.content[:1500],
                "execution_id": r.execution_id,
                "created_at": r.created_at.isoformat(),
            }
            for _, r in scored[:k]
        ]

    async def history(self, repository_id: str, limit: int = 50) -> list[HistoricalMemory]:
        async with self.db.session() as s:
            return list(
                await s.scalars(
                    select(HistoricalMemory)
                    .where(HistoricalMemory.repository_id == repository_id)
                    .order_by(HistoricalMemory.created_at.desc())
                    .limit(limit)
                )
            )

    async def forget_repository(self, repository_id: str) -> None:
        async with self.db.session() as s:
            await s.execute(delete(RepositoryMemory).where(RepositoryMemory.repository_id == repository_id))
            await s.execute(delete(HistoricalMemory).where(HistoricalMemory.repository_id == repository_id))

    async def purge_history(self, days: int) -> int:
        cutoff = utcnow() - timedelta(days=days)
        async with self.db.session() as s:
            result = await s.execute(delete(HistoricalMemory).where(HistoricalMemory.created_at < cutoff))
            return int(result.rowcount or 0)  # type: ignore[attr-defined]
