"""Application-level idempotency for task handlers backed by Redis.

The ``@idempotent`` decorator complements scheduling-level dedup
(``dispatch_task(..., dedup_key=...)``) by also blocking duplicate
*execution* — Cloud Tasks retries on the same task name still hit the
handler, and this is the only thing that stops them from running twice.

Pattern:
    1. Compute an idempotency key from the call arguments.
    2. ``SETNX`` the key in Redis with a TTL roughly equal to the p99
       expected runtime of the handler.
    3. If the key was already set, short-circuit with a
       ``{"status": "deduplicated", ...}`` response.

The lock is intentionally not released on completion — the TTL is the
retry-suppression window. Pick TTL too short and a slow task can finish,
the lock expires, and a queued retry starts a parallel run. Pick it too
long and legitimate re-dispatches have to wait. Tune per call site.
"""

from functools import wraps
from logging import getLogger
from typing import Any, Callable

import redis.exceptions

from app.integrations.redis_client import get_redis_client

logger = getLogger(__name__)


def idempotent(
    key: Callable[..., str],
    ttl_seconds: int = 3600,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Wrap a task handler with a Redis-backed SETNX lock.

    Args:
        key: Function that receives the same ``*args, **kwargs`` as the
            wrapped handler and returns the idempotency key string. The
            decorator prefixes it with ``idem:`` so callers don't have to.
        ttl_seconds: Lifetime of the lock. Aim for ~p99 of the handler's
            real runtime; defaults to 1h.

    Behaviour when Redis is unreachable
    ----------------------------------
    Fail open: log the error and run the handler without dedup.  Cloud
    Tasks delivers at-least-once anyway, so duplicate execution under
    Redis outage is no worse than the baseline guarantee — and far better
    than 500-ing every retry, which is what happens if we let the
    connection error propagate.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                lock_key = f"idem:{key(*args, **kwargs)}"
            except Exception:
                logger.exception(
                    "Idempotency key function raised; running %s without dedup",
                    getattr(func, "__name__", "<unknown>"),
                )
                return func(*args, **kwargs)

            try:
                acquired = get_redis_client().set(lock_key, "1", nx=True, ex=ttl_seconds)
            except (redis.exceptions.RedisError, OSError) as exc:
                logger.warning(
                    "Idempotency Redis unreachable; running %s without dedup: %s",
                    getattr(func, "__name__", "<unknown>"),
                    exc,
                )
                return func(*args, **kwargs)

            if not acquired:
                logger.info(
                    "Task deduplicated by idempotency lock",
                    extra={"handler": getattr(func, "__name__", "<unknown>"), "lock_key": lock_key},
                )
                return {"status": "deduplicated", "lock_key": lock_key}

            return func(*args, **kwargs)

        return wrapper

    return decorator
