import contextlib
from datetime import datetime, timezone
from typing import cast

import redis.exceptions
from celery import shared_task

from app.constants.celery_tasks import CeleryTask
from app.database import SessionLocal
from app.integrations.redis_client import get_redis_client
from app.services.sdk.sleep_service import (
    active_users_key,
    finish_sleep,
    is_ready_to_finish,
    load_sleep_states,
)
from app.utils.structured_logging import get_logger

logger = get_logger(__name__)


@shared_task(name=CeleryTask.FINALIZE_STALE_SLEEPS)
def finalize_stale_sleeps() -> None:
    """No-op when Redis isn't configured.

    Apple HealthKit "active sleep tracking" stores state in Redis (active_users
    SET + per-user state).  In Cloud-Tasks-backed deployments without Redis
    (axlbrains prod), there's no Redis to read, so there are no active users to
    finalise.  Fail open instead of crashing the hourly Cloud Scheduler call.
    """
    now = datetime.now(timezone.utc)
    redis_client = get_redis_client()

    try:
        active_users = list(cast("set[str]", redis_client.smembers(active_users_key())))
    except (redis.exceptions.RedisError, OSError) as exc:
        logger.warning("finalize_stale_sleeps: Redis unreachable, skipping", exc_info=exc)
        return

    with SessionLocal() as db:
        for user_id in active_users:
            try:
                # Skip users whose upload is currently in progress.
                lock = redis_client.lock(f"sleep:lock:{user_id}", timeout=30, blocking_timeout=0)
                if not lock.acquire(blocking=False):
                    continue

                try:
                    states = load_sleep_states(user_id)
                    if not states:
                        redis_client.srem(active_users_key(), user_id)
                    for state in states.values():
                        if is_ready_to_finish(state, now):
                            finish_sleep(db, user_id, state)
                finally:
                    with contextlib.suppress(Exception):
                        lock.release()

            except Exception as e:
                logger.error("Error finalizing stale sleep", exc_info=e, user_id=user_id)
