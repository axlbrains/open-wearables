"""Postgres-backed Redis-compatible key-value store.

A drop-in replacement for ``redis.Redis`` covering the subset of commands the
codebase actually uses: GET/SET/SETEX/EXPIRE/INCR/DELETE/MGET, SADD/SMEMBERS/
SREM, LPUSH/LRANGE/LTRIM, plus pipeline/lock/scan/pubsub stubs so existing
call sites work unchanged.

Backed by three tables (see ``alembic`` migration ``kv_store_tables``):

- ``kv_entry``       — string keys with optional ``expires_at``
- ``kv_set_member``  — set memberships (TTL is per-set; mirrored on each row)
- ``kv_list_entry``  — list values, total order via ``BIGSERIAL`` id

Trade-offs vs real Redis:

- Each operation hits Postgres.  Write-heavy hot loops (e.g. live HealthKit
  sleep recording with many state writes per second) will be slower than
  Redis but well within budget for OW's actual traffic.
- ``EXPIRE``/TTL is enforced lazily — readers skip rows where
  ``expires_at < now()``.  A daily ``vacuum_kv_expired`` cron removes them.
- ``publish`` is a no-op; ``pubsub`` returns a stub that yields nothing.
  The SSE streaming endpoints in ``sync_status_service`` will accept
  subscriptions but never deliver messages.  Move to Postgres LISTEN/NOTIFY
  if SSE consumers materialise.
- ``lock`` is implemented via SET-NX-EX semantics on ``kv_entry``.  Good
  enough for OW's coarse-grained per-user locks (Apple sleep upload guard,
  etc.).  Not Redlock-grade; don't use for cross-region critical sections.

The module exports ``KvStoreClient`` which mimics enough of the ``redis.Redis``
shape that ``app/integrations/redis_client.py`` can return it interchangeably.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expires_at(ex: int | None) -> datetime | None:
    if ex is None:
        return None
    return _now() + timedelta(seconds=int(ex))


class _Pipeline:
    """Best-effort pipeline.  Queues commands and replays them on ``execute()``.

    Mirrors Redis ``pipeline(transaction=False)`` semantics: each queued
    command runs independently — a failure on one doesn't cascade and
    abort the rest.  We log the exception and move on.  Real Redis with
    ``transaction=True`` would wrap MULTI/EXEC; we don't bother since none
    of our call sites pass it.
    """

    def __init__(self, client: "KvStoreClient") -> None:
        self._client = client
        self._ops: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def queued(*args: Any, **kwargs: Any) -> "_Pipeline":
            self._ops.append((name, args, kwargs))
            return self

        return queued

    def execute(self) -> list[Any]:
        results: list[Any] = []
        for name, args, kwargs in self._ops:
            method = getattr(self._client, name, None)
            if method is None:
                logger.warning("kv_store pipeline: unknown op %r — skipping", name)
                results.append(None)
                continue
            try:
                results.append(method(*args, **kwargs))
            except Exception as exc:
                logger.warning("kv_store pipeline op %r failed: %s", name, exc, exc_info=True)
                results.append(exc)
        self._ops.clear()
        return results


class _Lock:
    """Best-effort lock implemented via SET-NX-EX semantics.

    ``acquire(blocking=False)`` is the only mode we exercise — call sites
    in OW always pass ``blocking_timeout=0`` (Apple sleep upload guard,
    finalize_stale_sleeps loop).  Blocking acquisition would need a wait
    loop; not implemented because nothing needs it today.
    """

    def __init__(self, client: "KvStoreClient", key: str, timeout: int, blocking_timeout: int) -> None:
        self._client = client
        self._key = f"lock:{key}"
        self._timeout = timeout
        self._blocking_timeout = blocking_timeout
        self._token = uuid4().hex
        self._acquired = False

    def acquire(self, blocking: bool = True, blocking_timeout: int | None = None) -> bool:
        if blocking and (blocking_timeout or self._blocking_timeout) > 0:
            logger.debug("kv_store: blocking lock acquisition not implemented; falling back to single try")
        ok = self._client.set(self._key, self._token, nx=True, ex=self._timeout)
        self._acquired = bool(ok)
        return self._acquired

    def release(self) -> None:
        if not self._acquired:
            return
        # Only delete if we still own it (CAS via WHERE value=token).
        with self._client._engine.begin() as conn:  # noqa: SLF001
            conn.execute(
                text("DELETE FROM kv_entry WHERE key = :k AND value = :v"),
                {"k": self._key, "v": self._token},
            )
        self._acquired = False

    def __enter__(self) -> "_Lock":
        self.acquire(blocking=False)
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.release()


class _NullPubSub:
    """No-op pub/sub.  SSE streaming endpoints fall back to delivering
    nothing — replace with Postgres LISTEN/NOTIFY if real SSE consumers
    materialise.
    """

    def subscribe(self, *_channels: str) -> None:
        return None

    def unsubscribe(self, *_channels: str) -> None:
        return None

    def get_message(self, ignore_subscribe_messages: bool = False, timeout: float = 0.0) -> None:
        return None

    def close(self) -> None:
        return None


class KvStoreClient:
    """Postgres-backed Redis-shaped client.

    Construct via ``redis_client.get_redis_client()`` — the factory there
    picks this implementation when ``REDIS_HOST`` is unset.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._lock_pubsub = threading.Lock()

    # ------------------------------------------------------------------
    # Internal: connection-bound execution (used by pipeline)
    # ------------------------------------------------------------------

    def _call_with_conn(self, conn: Connection, name: str, args: tuple, kwargs: dict) -> Any:
        method = getattr(self, f"_{name}_conn", None)
        if method is None:
            # Fall back to single-shot execution outside the pipeline txn —
            # acceptable since we only pipeline for write-batches.
            return getattr(self, name)(*args, **kwargs)
        return method(conn, *args, **kwargs)

    # ------------------------------------------------------------------
    # String key/value
    # ------------------------------------------------------------------

    def get(self, key: str) -> str | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                text("SELECT value FROM kv_entry WHERE key = :k AND (expires_at IS NULL OR expires_at > now())"),
                {"k": key},
            ).first()
        return row[0] if row else None

    def mget(self, keys: Iterable[str]) -> list[str | None]:
        keys_list = list(keys)
        if not keys_list:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT key, value FROM kv_entry "
                    "WHERE key = ANY(CAST(:keys AS text[])) "
                    "AND (expires_at IS NULL OR expires_at > now())"
                ),
                {"keys": keys_list},
            ).fetchall()
        by_key = {r[0]: r[1] for r in rows}
        return [by_key.get(k) for k in keys_list]

    def set(self, key: str, value: Any, ex: int | None = None, nx: bool = False) -> bool:
        with self._engine.begin() as conn:
            return self._set_conn(conn, key, value, ex=ex, nx=nx)

    def _set_conn(self, conn: Connection, key: str, value: Any, ex: int | None = None, nx: bool = False) -> bool:
        val_str = value if isinstance(value, str) else str(value)
        exp = _expires_at(ex)
        if nx:
            # Insert only if absent (or if existing row has expired — clear
            # expired row first so NX semantics match Redis).
            conn.execute(
                text("DELETE FROM kv_entry WHERE key = :k AND expires_at IS NOT NULL AND expires_at <= now()"),
                {"k": key},
            )
            res = conn.execute(
                text(
                    "INSERT INTO kv_entry (key, value, expires_at) VALUES (:k, :v, :e) "
                    "ON CONFLICT (key) DO NOTHING RETURNING key"
                ),
                {"k": key, "v": val_str, "e": exp},
            ).first()
            return res is not None
        conn.execute(
            text(
                "INSERT INTO kv_entry (key, value, expires_at) VALUES (:k, :v, :e) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at"
            ),
            {"k": key, "v": val_str, "e": exp},
        )
        return True

    def setex(self, key: str, ttl: int, value: Any) -> bool:
        return self.set(key, value, ex=ttl)

    def expire(self, key: str, ttl: int) -> bool:
        exp = _expires_at(ttl)
        with self._engine.begin() as conn:
            res = conn.execute(
                text("UPDATE kv_entry SET expires_at = :e WHERE key = :k"),
                {"k": key, "e": exp},
            )
            updated = res.rowcount > 0
            # Also propagate TTL to set / list rows with the same key.
            conn.execute(
                text("UPDATE kv_set_member SET expires_at = :e WHERE set_key = :k"),
                {"k": key, "e": exp},
            )
            conn.execute(
                text("UPDATE kv_list_entry SET expires_at = :e WHERE list_key = :k"),
                {"k": key, "e": exp},
            )
        return updated

    def incr(self, key: str) -> int:
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    "INSERT INTO kv_entry (key, value) VALUES (:k, '1') "
                    "ON CONFLICT (key) DO UPDATE "
                    "SET value = CAST((CASE WHEN kv_entry.expires_at IS NOT NULL AND kv_entry.expires_at <= now() "
                    "                       THEN 0 ELSE CAST(kv_entry.value AS BIGINT) END) + 1 AS TEXT), "
                    "    expires_at = CASE WHEN kv_entry.expires_at IS NOT NULL AND kv_entry.expires_at <= now() "
                    "                      THEN NULL ELSE kv_entry.expires_at END "
                    "RETURNING value"
                ),
                {"k": key},
            ).first()
        return int(row[0])

    def delete(self, *keys: str) -> int:
        keys_list = list(keys)
        if not keys_list:
            return 0
        with self._engine.begin() as conn:
            res = conn.execute(
                text("DELETE FROM kv_entry WHERE key = ANY(CAST(:keys AS text[]))"),
                {"keys": keys_list},
            )
            # Also clean up any same-named sets/lists.  Redis DEL is type-aware
            # — calling it for a list deletes the list entirely; we mirror.
            conn.execute(
                text("DELETE FROM kv_set_member WHERE set_key = ANY(CAST(:keys AS text[]))"),
                {"keys": keys_list},
            )
            conn.execute(
                text("DELETE FROM kv_list_entry WHERE list_key = ANY(CAST(:keys AS text[]))"),
                {"keys": keys_list},
            )
        return res.rowcount

    # ------------------------------------------------------------------
    # Sets
    # ------------------------------------------------------------------

    def sadd(self, set_key: str, *members: str) -> int:
        if not members:
            return 0
        with self._engine.begin() as conn:
            res = conn.execute(
                text(
                    "INSERT INTO kv_set_member (set_key, member) "
                    "SELECT :sk, m FROM unnest(CAST(:members AS text[])) AS m "
                    "ON CONFLICT (set_key, member) DO NOTHING"
                ),
                {"sk": set_key, "members": list(members)},
            )
        return res.rowcount

    def smembers(self, set_key: str) -> set[str]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT member FROM kv_set_member "
                    "WHERE set_key = :sk AND (expires_at IS NULL OR expires_at > now())"
                ),
                {"sk": set_key},
            ).fetchall()
        return {r[0] for r in rows}

    def srem(self, set_key: str, *members: str) -> int:
        if not members:
            return 0
        with self._engine.begin() as conn:
            res = conn.execute(
                text("DELETE FROM kv_set_member WHERE set_key = :sk AND member = ANY(CAST(:m AS text[]))"),
                {"sk": set_key, "m": list(members)},
            )
        return res.rowcount

    # ------------------------------------------------------------------
    # Lists
    # ------------------------------------------------------------------

    def lpush(self, list_key: str, *values: str) -> int:
        if not values:
            return 0
        with self._engine.begin() as conn:
            self._lpush_conn(conn, list_key, *values)
            row = conn.execute(
                text("SELECT count(*) FROM kv_list_entry WHERE list_key = :lk"),
                {"lk": list_key},
            ).first()
        return int(row[0]) if row else 0

    def _lpush_conn(self, conn: Connection, list_key: str, *values: str) -> int:
        # Each value gets a row with a fresh BIGSERIAL id; LRANGE reads in
        # ``ORDER BY id DESC``, so the last LPUSH is at index 0 (head).
        for v in values:
            conn.execute(
                text("INSERT INTO kv_list_entry (list_key, value) VALUES (:lk, :v)"),
                {"lk": list_key, "v": v if isinstance(v, str) else str(v)},
            )
        return len(values)

    def lrange(self, list_key: str, start: int, end: int) -> list[str]:
        # ``end = -1`` means "to the end" in Redis; emulate with a large LIMIT.
        limit = None
        if end >= 0:
            limit = max(0, end - start + 1)
        with self._engine.connect() as conn:
            stmt = (
                "SELECT value FROM kv_list_entry "
                "WHERE list_key = :lk AND (expires_at IS NULL OR expires_at > now()) "
                "ORDER BY id DESC OFFSET :offset"
            )
            params: dict[str, Any] = {"lk": list_key, "offset": max(0, start)}
            if limit is not None:
                stmt += " LIMIT :limit"
                params["limit"] = limit
            rows = conn.execute(text(stmt), params).fetchall()
        return [r[0] for r in rows]

    def ltrim(self, list_key: str, start: int, end: int) -> bool:
        if start != 0 or end < 0:
            logger.debug("kv_store: ltrim with non-prefix range (%s..%s) — partial support", start, end)
        keep = max(0, end - start + 1) if end >= 0 else None
        with self._engine.begin() as conn:
            if keep is None:
                # No-op when end is negative — Redis "to the end" semantics.
                return True
            conn.execute(
                text(
                    "DELETE FROM kv_list_entry "
                    "WHERE list_key = :lk AND id NOT IN ("
                    "  SELECT id FROM kv_list_entry "
                    "  WHERE list_key = :lk ORDER BY id DESC LIMIT :keep"
                    ")"
                ),
                {"lk": list_key, "keep": keep},
            )
        return True

    # ------------------------------------------------------------------
    # Scan (pattern matching) — used by sync_status_service to enumerate
    # users with recent sync data.
    # ------------------------------------------------------------------

    def scan(self, cursor: int = 0, match: str | None = None, count: int = 100) -> tuple[int, list[str]]:
        # Redis SCAN is iterator-style with an opaque cursor; we don't paginate
        # in Postgres queries here — single-shot return, cursor always 0 on
        # both input and output to signal "no more pages".
        if match is None:
            pattern_filter = ""
            params: dict[str, Any] = {}
        else:
            pattern_filter = "WHERE key LIKE :p"
            params = {"p": match.replace("*", "%").replace("?", "_")}
        sql = (
            f"SELECT key FROM kv_entry {pattern_filter} "
            f"{'AND' if match else 'WHERE'} (expires_at IS NULL OR expires_at > now())"
        )
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return 0, [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Pipeline / lock / pubsub
    # ------------------------------------------------------------------

    def pipeline(self, transaction: bool = True) -> _Pipeline:  # noqa: ARG002 - signature compat
        return _Pipeline(self)

    def lock(self, key: str, timeout: int = 30, blocking_timeout: int = 0) -> _Lock:
        return _Lock(self, key, timeout=timeout, blocking_timeout=blocking_timeout)

    def publish(self, _channel: str, _message: str) -> int:
        # No-op.  See module docstring.
        return 0

    def pubsub(self, **_kwargs: Any) -> _NullPubSub:
        return _NullPubSub()

    # ------------------------------------------------------------------
    # Misc compatibility
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        with self._engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True

    def close(self) -> None:
        return None
