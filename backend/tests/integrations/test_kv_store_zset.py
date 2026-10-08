"""KvStoreClient sorted sets, and the sync-run index that needs them.

Prod has no Redis, so sync_status_service's run index (ZADD/ZREVRANGE) lands on the
Postgres-backed KvStore. Without sorted sets the index writes were skipped and
/sync/runs answered 500 with ``'KvStoreClient' object has no attribute 'zrevrange'``.
"""

from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.integrations.kv_store import KvStoreClient
from app.services import sync_status_service


@pytest.fixture
def kv(engine: Any) -> KvStoreClient:
    # The test schema comes from the ORM models; the KvStore tables only exist
    # through their migrations, so create the ones these tests touch.
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS kv_entry "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at TIMESTAMPTZ)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS kv_list_entry "
                "(id BIGSERIAL PRIMARY KEY, list_key TEXT NOT NULL, value TEXT NOT NULL, expires_at TIMESTAMPTZ)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS kv_set_member "
                "(set_key TEXT NOT NULL, member TEXT NOT NULL, expires_at TIMESTAMPTZ, "
                "PRIMARY KEY (set_key, member))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS kv_zset_member "
                "(zset_key TEXT NOT NULL, member TEXT NOT NULL, score DOUBLE PRECISION NOT NULL, "
                "expires_at TIMESTAMPTZ, PRIMARY KEY (zset_key, member))"
            )
        )
    return KvStoreClient(engine)


def _key() -> str:
    # The test database is shared for the session and KvStore commits on its own.
    return f"test:zset:{uuid4()}"


class TestSortedSet:
    def test_zadd_counts_only_new_members_and_updates_scores(self, kv: KvStoreClient) -> None:
        key = _key()

        assert kv.zadd(key, {"a": 1, "b": 2}) == 2
        assert kv.zadd(key, {"a": 5, "c": 3}) == 1

        assert kv.zscore(key, "a") == 5
        assert kv.zcard(key) == 3

    def test_nx_keeps_existing_scores(self, kv: KvStoreClient) -> None:
        key = _key()
        kv.zadd(key, {"a": 1})

        kv.zadd(key, {"a": 9, "b": 2}, nx=True)

        assert kv.zscore(key, "a") == 1
        assert kv.zscore(key, "b") == 2

    def test_xx_only_updates(self, kv: KvStoreClient) -> None:
        key = _key()
        kv.zadd(key, {"a": 1})

        kv.zadd(key, {"a": 9, "b": 2}, xx=True)

        assert kv.zscore(key, "a") == 9
        assert kv.zscore(key, "b") is None

    def test_range_order_ties_and_negative_indexes(self, kv: KvStoreClient) -> None:
        key = _key()
        kv.zadd(key, {"c": 3, "a": 1, "b2": 2, "b1": 2})

        assert kv.zrange(key, 0, -1) == ["a", "b1", "b2", "c"]
        assert kv.zrevrange(key, 0, -1) == ["c", "b2", "b1", "a"]
        assert kv.zrevrange(key, 1, 2) == ["b2", "b1"]
        assert kv.zrange(key, -2, -1) == ["b2", "c"]
        assert kv.zrevrange(key, 0, 0, withscores=True) == [("c", 3.0)]
        assert kv.zrange(key, 3, 1) == []
        assert kv.zrevrange(_key(), 0, 10) == []

    def test_zremrangebyscore_bounds(self, kv: KvStoreClient) -> None:
        key = _key()
        kv.zadd(key, {"a": 1, "b": 2, "c": 3, "d": 4})

        assert kv.zremrangebyscore(key, "-inf", "(2") == 1
        assert kv.zrange(key, 0, -1) == ["b", "c", "d"]
        assert kv.zremrangebyscore(key, 3, "+inf") == 2
        assert kv.zrange(key, 0, -1) == ["b"]

    def test_zremrangebyrank_keeps_the_newest(self, kv: KvStoreClient) -> None:
        """The run index trims with ``zremrangebyrank(key, 0, -(MAX + 1))``."""
        key = _key()
        kv.zadd(key, {f"r{i}": i for i in range(5)})

        assert kv.zremrangebyrank(key, 0, -(3 + 1)) == 2

        assert kv.zrange(key, 0, -1) == ["r2", "r3", "r4"]

    def test_zrem(self, kv: KvStoreClient) -> None:
        key = _key()
        kv.zadd(key, {"a": 1, "b": 2})

        assert kv.zrem(key, "a", "missing") == 1
        assert kv.zrange(key, 0, -1) == ["b"]

    def test_expire_and_delete_cover_sorted_sets(self, kv: KvStoreClient, engine: Any) -> None:
        key = _key()
        kv.zadd(key, {"a": 1})

        assert kv.expire(key, 600) is True
        assert kv.zcard(key) == 1

        # Expired members disappear from reads and do not count as existing on re-add.
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE kv_zset_member SET expires_at = now() - interval '1 second' WHERE zset_key = :k"),
                {"k": key},
            )
        assert kv.zcard(key) == 0
        assert kv.zadd(key, {"a": 2}) == 1

        kv.delete(key)
        assert kv.zcard(key) == 0

    def test_new_member_joins_the_set_ttl(self, kv: KvStoreClient, engine: Any) -> None:
        key = _key()
        kv.zadd(key, {"a": 1})
        kv.expire(key, 600)

        kv.zadd(key, {"b": 2})

        with engine.connect() as conn:
            missing_ttl = conn.execute(
                text("SELECT count(*) FROM kv_zset_member WHERE zset_key = :k AND expires_at IS NULL"),
                {"k": key},
            ).scalar_one()
        assert missing_ttl == 0


def test_sync_run_index_works_on_kv_store(kv: KvStoreClient) -> None:
    """The /sync/runs path end to end: emit runs, then list them newest first."""
    user_id = uuid4()
    with (
        patch.object(sync_status_service, "get_redis_client", return_value=kv),
        patch.object(sync_status_service, "try_persist_run"),
        patch.object(sync_status_service, "_maybe_dispatch_outgoing_webhook"),
    ):
        first = sync_status_service.emit_sync_started(user_id, "polar", "pull")
        second = sync_status_service.emit_sync_started(user_id, "strava", "pull")

        summaries = sync_status_service.get_all_run_summaries(limit=10, user_id_filter=user_id)
        filtered = sync_status_service.get_all_run_summaries(limit=10, user_id_filter=user_id, provider_filter="polar")

    assert [s.run_id for s in summaries] == [second.run_id, first.run_id]
    assert [s.run_id for s in filtered] == [first.run_id]
