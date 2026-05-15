"""ARQ Redis connection settings and pool lifecycle.

The API process holds one ARQ pool (created in ``app.main`` lifespan) used to
enqueue jobs and to publish WebSocket events. The worker process gets its own
connection from ARQ via the task ``ctx['redis']``.
"""

from __future__ import annotations

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings


def get_redis_settings() -> RedisSettings:
    """ARQ RedisSettings parsed from the configured REDIS_URL."""
    return RedisSettings.from_dsn(get_settings().REDIS_URL)


async def create_arq_pool() -> ArqRedis:
    """Create an ARQ pool — used by the API process to enqueue jobs."""
    return await create_pool(get_redis_settings())
