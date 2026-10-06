"""KvStoreClient.eval runs the real Lua lock scripts the codebase sends to Redis.

Prod has no Redis, so these scripts reach the Postgres-backed KvStore. Each test
uses the script object from the module that sends it, so a reworded upstream
script fails here instead of on the first prod call.
"""

from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.integrations.kv_store import KvStoreClient
from app.services import dashboard_stats_cache, sync_coordination
from app.services.providers.garmin.backfill_state import core as garmin_backfill


@pytest.fixture
def kv(engine: Any) -> KvStoreClient:
    # The test schema comes from the ORM models; the KvStore tables only exist
    # through their migration (7c2b1f4a9e3d), so create the one eval touches.
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS kv_entry "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at TIMESTAMPTZ)"
            )
        )
    return KvStoreClient(engine)


def _key() -> str:
    # The test database is shared for the session and KvStore commits on its own.
    return f"test:eval:{uuid4()}"


class TestCompareAndDelete:
    @pytest.mark.parametrize(
        "script",
        [
            sync_coordination._RELEASE_LUA,
            garmin_backfill._RELEASE_LUA,
            # single-quoted; an exact-text match missed it (0.9.16)
            dashboard_stats_cache._RELEASE_IF_OWNER,
        ],
        ids=["sync_coordination", "garmin_backfill", "dashboard_stats_cache"],
    )
    def test_releases_only_when_owner(self, kv: KvStoreClient, script: str) -> None:
        key = _key()
        kv.set(key, "mine", ex=60)

        assert kv.eval(script, 1, key, "someone-else") == 0
        assert kv.get(key) == "mine"

        assert kv.eval(script, 1, key, "mine") == 1
        assert kv.get(key) is None


class TestCompareAndRenew:
    def test_extends_own_lease(self, kv: KvStoreClient) -> None:
        key = _key()
        kv.set(key, "mine", ex=5)

        assert kv.eval(sync_coordination._RENEW_LUA, 1, key, "mine", 600) == 1
        assert kv.ttl(key) > 500

    def test_takes_back_a_lapsed_lease(self, kv: KvStoreClient) -> None:
        key = _key()

        assert kv.eval(sync_coordination._RENEW_LUA, 1, key, "mine", 600) == 1
        assert kv.get(key) == "mine"

    def test_refuses_a_lease_held_by_someone_else(self, kv: KvStoreClient) -> None:
        key = _key()
        kv.set(key, "theirs", ex=600)

        assert kv.eval(sync_coordination._RENEW_LUA, 1, key, "mine", 600) == 0
        assert kv.get(key) == "theirs"


def test_unknown_script_still_fails_loudly(kv: KvStoreClient) -> None:
    with pytest.raises(NotImplementedError):
        kv.eval("return redis.call('incr', KEYS[1])", 1, _key())
