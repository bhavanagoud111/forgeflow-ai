"""Standalone worker process: ``uv run forgeflow-worker``.

Use it when the API runs with ``FORGEFLOW_EMBEDDED_WORKER=false`` (for example in Docker
Compose) so API and execution scale independently.
"""

from __future__ import annotations

import asyncio
import logging
import signal

from forgeflow.config import get_settings
from forgeflow.container import build_container
from forgeflow.orchestration.engine import Worker


async def _amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    c = await build_container(settings)
    worker = Worker(c.engine, settings.max_parallel_tasks)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, worker.stop)
    logging.getLogger("forgeflow").info("worker %s started", worker.id)
    try:
        await worker.run_forever()
    finally:
        await c.close()


def main() -> None:
    asyncio.run(_amain())
