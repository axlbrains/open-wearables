"""Tests for filling distance / energy on Health Connect workouts from in-window records.

See scripts/data_migrations/backfill_health_connect_workout_totals.py.
"""

import importlib.util
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy.orm import Session

from app.models import SeriesTypeDefinition, User, WorkoutDetails
from app.schemas.enums import SeriesType
from app.schemas.enums.provider import ProviderName
from app.schemas.enums.series_types import get_series_type_id
from tests.factories import (
    DataPointSeriesFactory,
    DataSourceFactory,
    EventRecordFactory,
    UserFactory,
    WorkoutDetailsFactory,
)

_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "data_migrations" / "backfill_health_connect_workout_totals.py"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("backfill_health_connect_workout_totals", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backfill = _load_module().backfill

T0 = datetime(2026, 9, 18, 12, 44, 0, tzinfo=timezone.utc)
DURATION = timedelta(minutes=57)
FITBIT = "com.fitbit.FitbitMobile"


def _workout(db: Session, **detail: Any) -> tuple[Any, Any]:
    """A session plus the record-side data_source Health Connect gives the same app."""
    user = UserFactory()
    session_source = DataSourceFactory(
        user=user, provider=ProviderName.HEALTH_CONNECT, source=FITBIT, device_model="Fitbit Android App"
    )
    record = EventRecordFactory(
        data_source=session_source, type="running", start_datetime=T0, end_datetime=T0 + DURATION
    )
    WorkoutDetailsFactory(event_record=record, **{"distance": None, "energy_burned": Decimal("0"), **detail})
    records_source = DataSourceFactory(
        user=user, provider=ProviderName.HEALTH_CONNECT, source=FITBIT, device_model=None
    )
    return record, records_source


def _series(db: Session, source: Any, series: SeriesType, values: list[float], start: datetime = T0) -> None:
    definition = db.get(SeriesTypeDefinition, get_series_type_id(series))
    for i, value in enumerate(values):
        DataPointSeriesFactory(
            data_source=source,
            series_type=definition,
            recorded_at=start + timedelta(minutes=i + 1),
            value=Decimal(str(value)),
            is_daily_total=False,
        )


def _detail(db: Session, record: Any) -> WorkoutDetails:
    db.expire_all()
    return db.query(WorkoutDetails).filter(WorkoutDetails.record_id == record.id).one()


class TestBackfill:
    def test_fills_distance_and_energy_from_the_apps_records(self, db: Session) -> None:
        # Arrange
        record, source = _workout(db)
        _series(db, source, SeriesType.distance_walking_running, [1000.0, 2000.0, 2278.0])
        _series(db, source, SeriesType.active_energy, [120.0, 180.0])

        # Act
        counts = backfill(db, dry_run=False)

        # Assert
        detail = _detail(db, record)
        assert detail.distance == Decimal("5278")
        assert detail.energy_burned == Decimal("300")
        assert counts["filled"] == 1

    def test_duplicated_distance_series_are_not_added_up(self, db: Session) -> None:
        """The SDK reads each DistanceRecord as walking/running AND as cycling distance."""
        # Arrange
        record, source = _workout(db)
        _series(db, source, SeriesType.distance_walking_running, [5000.0])
        _series(db, source, SeriesType.distance_cycling, [5000.0])

        # Act
        backfill(db, dry_run=False)

        # Assert
        assert _detail(db, record).distance == Decimal("5000")

    def test_zero_energy_becomes_null_when_nothing_was_recorded(self, db: Session) -> None:
        # Arrange
        record, _ = _workout(db)

        # Act
        counts = backfill(db, dry_run=False)

        # Assert
        assert _detail(db, record).energy_burned is None
        assert counts["zeroed_energy_nulled"] == 1

    def test_never_overwrites_a_sent_figure(self, db: Session) -> None:
        # Arrange
        record, source = _workout(db, distance=Decimal("4200"), energy_burned=Decimal("410"))
        _series(db, source, SeriesType.distance_walking_running, [5000.0])

        # Act
        backfill(db, dry_run=False)

        # Assert
        detail = _detail(db, record)
        assert (detail.distance, detail.energy_burned) == (Decimal("4200"), Decimal("410"))

    def test_other_apps_and_records_outside_the_window_are_ignored(self, db: Session) -> None:
        # Arrange
        record, source = _workout(db)
        other_app = DataSourceFactory(
            user=db.get(User, source.user_id),
            provider=ProviderName.HEALTH_CONNECT,
            source="com.sec.android.app.shealth",
        )
        _series(db, other_app, SeriesType.distance_walking_running, [3000.0])
        _series(db, source, SeriesType.distance_walking_running, [3000.0], start=T0 - timedelta(hours=2))

        # Act
        backfill(db, dry_run=False)

        # Assert
        assert _detail(db, record).distance is None

    def test_dry_run_and_rerun_change_nothing(self, db: Session) -> None:
        # Arrange
        record, source = _workout(db)
        _series(db, source, SeriesType.distance_walking_running, [5000.0])

        # Act
        backfill(db, dry_run=True)
        dry = _detail(db, record).distance
        backfill(db, dry_run=False)
        second = backfill(db, dry_run=False)

        # Assert
        assert dry is None
        assert second["filled"] == 0
        assert second["zeroed_energy_nulled"] == 0
