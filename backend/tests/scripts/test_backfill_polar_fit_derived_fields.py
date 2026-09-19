"""Tests for filling elev_high / elev_low / steps_count from stored Polar samples.

See scripts/data_migrations/backfill_polar_fit_derived_fields.py.
"""

import importlib.util
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy.orm import Session

from app.models import SeriesTypeDefinition, WorkoutDetails
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
    Path(__file__).resolve().parents[2] / "scripts" / "data_migrations" / "backfill_polar_fit_derived_fields.py"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("backfill_polar_fit_derived_fields", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backfill = _load_module().backfill

T0 = datetime(2026, 9, 19, 8, 0, 0, tzinfo=timezone.utc)
DURATION = timedelta(seconds=60)


def _workout(db: Session, *, workout_type: str = "running", **detail: Any) -> tuple[Any, Any]:
    source = DataSourceFactory(user=UserFactory(), provider=ProviderName.POLAR, source="polar")
    record = EventRecordFactory(data_source=source, type=workout_type, start_datetime=T0, end_datetime=T0 + DURATION)
    # The factory pre-fills some of these; start from "the FIT left them out".
    fields = {"elev_low": None, "elev_high": None, "steps_count": None, **detail}
    WorkoutDetailsFactory(event_record=record, **fields)
    return record, source


def _samples(db: Session, source: Any, series: SeriesType, values: list[float], start: datetime = T0) -> None:
    definition = db.get(SeriesTypeDefinition, get_series_type_id(series))
    for i, value in enumerate(values):
        DataPointSeriesFactory(
            data_source=source,
            series_type=definition,
            recorded_at=start + timedelta(seconds=i),
            value=Decimal(str(value)),
        )


def _detail(db: Session, record: Any) -> WorkoutDetails:
    db.expire_all()
    return db.query(WorkoutDetails).filter(WorkoutDetails.record_id == record.id).one()


class TestBackfill:
    def test_fills_span_and_steps_from_samples(self, db: Session) -> None:
        # Arrange: 60 one-second cadence samples at 80 strides/min
        record, source = _workout(db)
        _samples(db, source, SeriesType.elevation, [30.0, 55.5, 41.0])
        _samples(db, source, SeriesType.cadence, [80.0] * 60)

        # Act
        counts = backfill(db, dry_run=False)

        # Assert
        detail = _detail(db, record)
        assert detail.elev_low == Decimal("30")
        assert detail.elev_high == Decimal("55.5")
        assert detail.steps_count == round(80 * 59 / 60 * 2)
        assert counts["filled"] == 1

    def test_never_overwrites_a_device_figure(self, db: Session) -> None:
        # Arrange
        record, source = _workout(db, elev_low=Decimal("1"), elev_high=Decimal("2"), steps_count=999)
        _samples(db, source, SeriesType.elevation, [30.0, 55.5])
        _samples(db, source, SeriesType.cadence, [80.0] * 60)

        # Act
        backfill(db, dry_run=False)

        # Assert
        detail = _detail(db, record)
        assert (detail.elev_low, detail.elev_high, detail.steps_count) == (Decimal("1"), Decimal("2"), 999)

    def test_no_steps_off_foot(self, db: Session) -> None:
        """Cycling cadence is pedal rpm."""
        # Arrange
        record, source = _workout(db, workout_type="cycling")
        _samples(db, source, SeriesType.cadence, [80.0] * 60)

        # Act
        backfill(db, dry_run=False)

        # Assert
        assert _detail(db, record).steps_count is None

    def test_samples_outside_the_window_are_not_used(self, db: Session) -> None:
        """A row stored before the UTC-offset fix has its samples at another time."""
        # Arrange
        record, source = _workout(db)
        _samples(db, source, SeriesType.elevation, [30.0, 55.5], start=T0 - timedelta(hours=4))

        # Act
        counts = backfill(db, dry_run=False)

        # Assert
        assert _detail(db, record).elev_high is None
        assert counts["nothing_to_fill"] == 1

    def test_dry_run_and_rerun_change_nothing(self, db: Session) -> None:
        # Arrange
        record, source = _workout(db)
        _samples(db, source, SeriesType.elevation, [30.0, 55.5])

        # Act
        backfill(db, dry_run=True)
        dry = _detail(db, record).elev_high
        backfill(db, dry_run=False)
        second = backfill(db, dry_run=False)

        # Assert
        assert dry is None
        assert second["filled"] == 0
