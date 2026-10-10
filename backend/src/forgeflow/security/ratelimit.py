"""Fixed-window rate limiter backed by Redis when configured, memory otherwise."""

from __future__ import annotations

import time
from collections import defaultdict

from redis.asyncio import Redis


class RateLimiter:
    def __init__(self, per_minute: int, redis_url: str | None = None) -> None:
        self.per_minute = per_minute
        self._redis: Redis | None = Redis.from_url(redis_url) if redis_url else None
        self._counts: dict[tuple[str, int], int] = defaultdict(int)

    async def hit(self, key: str) -> bool:
        """Record a request; return False when the caller is over the limit."""
        window = int(time.time() // 60)
        if self._redis is not None:
            rkey = f"forgeflow:rl:{key}:{window}"
            count = await self._redis.incr(rkey)
            if count == 1:
                await self._redis.expire(rkey, 90)
            return int(count) <= self.per_minute
        self._counts[(key, window)] += 1
        if len(self._counts) > 10_000:
            for k in [k for k in self._counts if k[1] < window]:
                del self._counts[k]
        return self._counts[(key, window)] <= self.per_minute
