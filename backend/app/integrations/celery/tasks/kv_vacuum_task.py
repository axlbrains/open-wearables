"""Daily vacuum of expired ``kv_*`` rows.

``KvStoreClient`` writes ``expires_at`` and readers skip past-expiry rows on
the fly, so correctness doesn't depend on this task running.  Its job is to
keep the tables from accumulating dead rows indefinitely — without it, every
expired set member / list entry / key would sit forever even though no reader
returns it.

Scheduled via Cloud Scheduler at 02:30 UTC (see scheduler_jobs in tfvars).
"""

from logging import getLogger

from celery import shared_task
from sqlalchemy import text

from app.database import engine

logger = getLogger(__name__)


@shared_task
def vacuum_kv_expired() -> dict[str, int]:
    """Remove past-expiry rows from kv_entry / kv_set_member / kv_list_entry."""
    deleted: dict[str, int] = {}
    with engine.begin() as conn:
        for table in ("kv_entry", "kv_set_member", "kv_list_entry"):
            res = conn.execute(text(f"DELETE FROM {table} WHERE expires_at IS NOT NULL AND expires_at < now()"))
            deleted[table] = res.rowcount
    total = sum(deleted.values())
    if total > 0:
        logger.info("kv_store vacuum: removed %s rows: %s", total, deleted)
    return deleted
