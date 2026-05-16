from collections.abc import AsyncGenerator, Iterator
from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy import UUID as SQL_UUID
from sqlalchemy import Date, DateTime, Engine, String, Text, create_engine, func, inspect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declared_attr,
    mapped_column,
    sessionmaker,
)

from app.config import settings
from app.schemas.auth import ConnectionStatus, LiveSyncMode, TokenType
from app.schemas.enums import AggregationMethod, HealthScoreCategory, ProviderName
from app.schemas.model_crud.user_management import InvitationStatus
from app.utils.mappings_meta import AutoRelMeta

# Per-Cloud-Run-instance pool sizing.
#
# Cloud SQL Postgres has a hard ``max_connections`` cap (~100 on
# ``db-custom-1-3840``).  Each Cloud Run instance opens its own pool,
# and we run **two** engines (sync + async) per instance, so the
# per-instance budget is roughly:
#     (pool_size + max_overflow) * 2
# Long-lived endpoints (sync-status SSE) plus new periodic tasks
# (provider webhook registration, Oura renewal) need more headroom
# than the original db-f1-micro era 2+3 pool — that was sized for a
# 25-conn DB.
#
# pool_size=5, max_overflow=30 ⇒ ≤ 35 conns per engine ⇒ ≤ 70 per
# instance.  At 100-conn DB that's headroom for one warm instance to
# absorb axl-api fan-out bursts (Promise.all × 6 active users × 4
# endpoints) without serialising on pool waits.  See OW issue #13.
#
# pool_timeout=10s replaces the old 30s — endpoints that already
# perform 4 sequential DB calls used to stack into 30 / 60 / 120s
# 500s when the pool was hot.  Failing fast keeps the worst case to
# ~40s and surfaces saturation as a clean error instead of a stall.
#
# pool_recycle=300s (5 min) drops idle connections aggressively so
# instances that briefly scaled up don't sit on slots they're not
# actively using.
#
# statement_timeout=30s is a backstop against runaway queries — pool
# wait is bounded by pool_timeout, this covers the per-query side.
_PG_CONNECT_ARGS = {"options": "-c statement_timeout=30000"}

engine = create_engine(
    settings.db_uri,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=30,
    pool_timeout=10,
    pool_recycle=300,
    connect_args=_PG_CONNECT_ARGS,
)
async_engine = create_async_engine(
    settings.db_uri,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=30,
    pool_timeout=10,
    pool_recycle=300,
    connect_args=_PG_CONNECT_ARGS,
)


def _prepare_sessionmaker(engine: Engine) -> sessionmaker:
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _prepare_async_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


class BaseDbModel(DeclarativeBase, metaclass=AutoRelMeta):
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    @declared_attr.directive
    def __tablename__(self) -> str:
        return self.__name__.lower()

    @property
    def id_str(self) -> str:
        return f"{inspect(self).identity[0]}"

    def __repr__(self) -> str:
        mapper = inspect(self.__class__)
        fields = [f"{col.key}={repr(getattr(self, col.key, None))}" for col in mapper.columns]
        return f"<{self.__class__.__name__}({', '.join(fields)})>"

    type_annotation_map = {
        str: Text,
        UUID: SQL_UUID,
        date: Date,
        datetime: DateTime(timezone=True),
        ConnectionStatus: String(64),
        LiveSyncMode: String(32),
        InvitationStatus: String(50),
        ProviderName: String(50),
        HealthScoreCategory: String(32),
        TokenType: String(64),
        AggregationMethod: String(32),
    }


SessionLocal = _prepare_sessionmaker(engine)
AsyncSessionLocal = _prepare_async_sessionmaker(async_engine)


def _get_db_dependency() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()


async def _get_async_db_dependency() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


DbSession = Annotated[Session, Depends(_get_db_dependency)]
AsyncDbSession = Annotated[AsyncSession, Depends(_get_async_db_dependency)]
