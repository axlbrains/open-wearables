"""Centralized Redis-shaped client for the application.

In deployments with a real Redis (``REDIS_HOST`` configured), returns a
plain ``redis.Redis``.  Otherwise — like axlbrains prod where everything is
Postgres / Cloud Tasks — falls back to ``KvStoreClient`` which speaks the
same API but persists to the OW database (see ``app/integrations/kv_store.py``).

Either way callers get the same surface, so the rest of the codebase stays
unchanged.
"""

from functools import lru_cache
from logging import getLogger
from typing import Any

import redis

from app.config import settings

logger = getLogger(__name__)


def _redis_configured() -> bool:
    """A real Redis is reachable only when the operator explicitly points us
    at one (host other than the ``"localhost"`` default, or a full
    ``REDIS_URL`` override).  Anything else means we should use the Postgres
    fallback — better than crashing on every call.
    """
    if settings.redis_url_override is not None:
        return True
    return settings.redis_host not in ("", "localhost", "127.0.0.1")


@lru_cache()
def get_redis_client() -> Any:
    """Singleton accessor for the Redis-shaped client.

    Returns a real ``redis.Redis`` when ``REDIS_HOST`` points to an actual
    server; falls back to the Postgres-backed ``KvStoreClient`` otherwise.
    The cached singleton means we resolve the backend once per process.
    """
    if _redis_configured():
        return redis.from_url(settings.redis_url, decode_responses=True)

    # Lazy import to avoid loading SQLAlchemy plumbing for callers that
    # would otherwise short-circuit at module import time on a worker that
    # only needs Redis for one-off tasks.
    from app.database import engine
    from app.integrations.kv_store import KvStoreClient

    logger.info("REDIS_HOST not configured — using Postgres-backed kv_store")
    return KvStoreClient(engine)
