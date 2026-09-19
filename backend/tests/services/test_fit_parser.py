from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import fitdecode
import pytest

from app.schemas.enums.series_types import SeriesType
from app.services.fit_parser import FitParseResult, estimate_steps, parse_fit_file
from tests.fixtures.fit_builder import SPORT_CYCLING, make_cycling_fit, make_running_fit, make_swimming_fit

USER_ID = uuid4()
DS_ID = uuid4()


@pytest.fixture(scope="module")
def running() -> FitParseResult:
    return parse_fit_file(make_running_fit(), USER_ID, DS_ID, source="garmin")


@pytest.fixture(scope="module")
def cycling() -> FitParseResult:
    return parse_fit_file(make_cycling_fit(), USER_ID, DS_ID, source="garmin")


@pytest.fixture(scope="module")
def swimming() -> FitParseResult:
    return parse_fit_file(make_swimming_fit(), USER_ID, DS_ID, source="garmin")


class TestRunning:
    def test_sample_count(self, running: FitParseResult) -> None:
        assert len(running.samples) > 0

    def test_expected_series_types(self, running: FitParseResult) -> None:
        types = {s.series_type for s in running.samples}
        assert SeriesType.heart_rate in types
        assert SeriesType.speed in types
        assert SeriesType.cadence in types
        assert SeriesType.power in types
        assert SeriesType.running_vertical_oscillation in types
        assert SeriesType.running_ground_contact_time in types
        assert SeriesType.latitude in types
        assert SeriesType.longitude in types
        assert SeriesType.elevation in types
        assert SeriesType.air_temperature in types
        assert SeriesType.running_vertical_ratio in types
        assert SeriesType.running_stance_time_balance in types

    def test_granularity_one_second(self, running: FitParseResult) -> None:
        hr = sorted(s.recorded_at for s in running.samples if s.series_type == SeriesType.heart_rate)
        gaps = [(hr[i + 1] - hr[i]).seconds for i in range(len(hr) - 1)]
        assert all(g == 1 for g in gaps)

    def test_heart_rate_values_in_range(self, running: FitParseResult) -> None:
        vals = [s.value for s in running.samples if s.series_type == SeriesType.heart_rate]
        assert all(Decimal(40) <= v <= Decimal(220) for v in vals)

    def test_speed_non_negative(self, running: FitParseResult) -> None:
        vals = [s.value for s in running.samples if s.series_type == SeriesType.speed]
        assert all(v >= Decimal(0) for v in vals)

    def test_vertical_oscillation_in_cm_range(self, running: FitParseResult) -> None:
        # FIT raw mm/10 → parser _scale(0.1) → cm; synthetic value 8.5 cm
        vals = [s.value for s in running.samples if s.series_type == SeriesType.running_vertical_oscillation]
        assert all(Decimal("0.1") <= v <= Decimal("30") for v in vals)

    def test_sample_metadata(self, running: FitParseResult) -> None:
        s = running.samples[0]
        assert s.user_id == USER_ID
        assert s.data_source_id == DS_ID
        assert s.source == "garmin"
        assert s.recorded_at is not None
        assert s.recorded_at.tzinfo is not None

    def test_gps_values_in_degree_range(self, running: FitParseResult) -> None:
        lats = [s.value for s in running.samples if s.series_type == SeriesType.latitude]
        lons = [s.value for s in running.samples if s.series_type == SeriesType.longitude]
        assert all(Decimal(-90) <= v <= Decimal(90) for v in lats)
        assert all(Decimal(-180) <= v <= Decimal(180) for v in lons)

    def test_elevation_in_meters(self, running: FitParseResult) -> None:
        vals = [s.value for s in running.samples if s.series_type == SeriesType.elevation]
        # synthetic: 200 m
        assert all(Decimal(0) <= v <= Decimal(9000) for v in vals)

    def test_temperature_in_celsius_range(self, running: FitParseResult) -> None:
        vals = [s.value for s in running.samples if s.series_type == SeriesType.air_temperature]
        # synthetic: 18°C
        assert all(Decimal(-50) <= v <= Decimal(60) for v in vals)

    def test_running_dynamics_in_range(self, running: FitParseResult) -> None:
        vr = [s.value for s in running.samples if s.series_type == SeriesType.running_vertical_ratio]
        stb = [s.value for s in running.samples if s.series_type == SeriesType.running_stance_time_balance]
        # synthetic: vertical_ratio=8.5%, stance_time_balance=49.5%
        assert all(Decimal(0) <= v <= Decimal(100) for v in vr)
        assert all(Decimal(0) <= v <= Decimal(100) for v in stb)


class TestCycling:
    def test_only_heart_rate(self, cycling: FitParseResult) -> None:
        assert {s.series_type for s in cycling.samples} == {SeriesType.heart_rate}

    def test_has_samples(self, cycling: FitParseResult) -> None:
        assert len(cycling.samples) > 0


class TestSwimming:
    def test_only_heart_rate(self, swimming: FitParseResult) -> None:
        assert {s.series_type for s in swimming.samples} == {SeriesType.heart_rate}


class TestSegments:
    def test_running_has_two_laps(self, running: FitParseResult) -> None:
        laps = [s for s in running.segments if s["kind"] == "lap"]
        assert len(laps) == 2

    def test_lap_required_fields(self, running: FitParseResult) -> None:
        for lap in running.segments:
            assert lap["kind"] == "lap"
            assert isinstance(lap["index"], int)
            assert lap["elapsed_seconds"] > 0
            assert lap["start_time"] is not None

    def test_lap_has_distance_and_hr(self, running: FitParseResult) -> None:
        lap = running.segments[0]
        assert "distance_meters" in lap
        assert lap["distance_meters"] > 0
        assert "avg_heart_rate" in lap
        assert 40 <= lap["avg_heart_rate"] <= 220
        assert "max_heart_rate" in lap
        assert lap["max_heart_rate"] >= lap["avg_heart_rate"]

    def test_lap_indices_sequential(self, running: FitParseResult) -> None:
        laps = [s for s in running.segments if s["kind"] == "lap"]
        indices = [lap["index"] for lap in laps]
        assert indices == list(range(len(laps)))

    def test_cycling_no_segments(self, cycling: FitParseResult) -> None:
        assert cycling.segments == []

    def test_swimming_no_segments(self, swimming: FitParseResult) -> None:
        assert swimming.segments == []


class TestInvalidInput:
    def test_empty_bytes_returns_no_samples(self) -> None:
        assert parse_fit_file(b"", uuid4(), uuid4()).samples == []

    def test_garbage_bytes_raises(self) -> None:
        with pytest.raises(fitdecode.FitError):
            parse_fit_file(b"not a fit file at all", uuid4(), uuid4())


class TestSessionSummary:
    """The FIT ``session`` message is the only whole-workout rollup some providers give us."""

    def test_running_has_a_session_summary(self, running: FitParseResult) -> None:
        assert running.session

    def test_summary_is_keyed_for_event_record_metrics(self, running: FitParseResult) -> None:
        """Keys must match EventRecordDetail field names so they merge without a translation step."""
        from app.schemas.model_crud.activities import EventRecordDetailCreate

        assert set(running.session) <= set(EventRecordDetailCreate.model_fields)

    def test_expected_rollup_values(self, running: FitParseResult) -> None:
        assert running.session["distance"] == Decimal("60.0")
        assert running.session["energy_burned"] == Decimal("320.0")
        assert running.session["heart_rate_avg"] == Decimal("154.0")
        assert running.session["heart_rate_max"] == 168
        assert running.session["average_speed"] == Decimal("3.2")
        assert running.session["max_speed"] == Decimal("4.1")
        assert running.session["average_cadence"] == Decimal("86.0")
        assert running.session["average_watts"] == Decimal("245.0")
        assert running.session["max_watts"] == Decimal("310.0")
        assert running.session["total_elevation_gain"] == Decimal("125.0")
        assert running.session["elev_high"] == Decimal("260.0")
        assert running.session["elev_low"] == Decimal("180.0")

    def test_timer_time_is_whole_seconds(self, running: FitParseResult) -> None:
        assert running.session["moving_time_seconds"] == 20

    def test_no_session_message_yields_empty_summary(self, cycling: FitParseResult) -> None:
        """A file without a session rollup must not invent one."""
        assert cycling.session == {}


class TestSessionFieldsFromSamples:
    """Fill session fields a device leaves out, from the samples it did record.

    Polar writes altitude on every record but no min/max in the session, and no step
    total at all. The device's own session figure always wins where it exists.
    """

    def test_device_altitude_span_wins_over_samples(self, running: FitParseResult) -> None:
        # The fixture's session says 180-260 m; its samples are a flat 200 m.
        assert running.session["elev_low"] == Decimal("180.0")
        assert running.session["elev_high"] == Decimal("260.0")

    def test_altitude_span_comes_from_samples_when_the_session_has_none(self) -> None:
        # Act
        result = parse_fit_file(make_running_fit(session_altitude=False), USER_ID, DS_ID)

        # Assert
        assert result.session["elev_low"] == Decimal("200.0")
        assert result.session["elev_high"] == Decimal("200.0")

    def test_steps_are_estimated_from_per_foot_cadence(self) -> None:
        # 85 strides/min for the 19 s between 20 one-second records, two feet per stride.
        result = parse_fit_file(make_running_fit(session_altitude=False), USER_ID, DS_ID)
        assert result.session["steps_count"] == round(85 * 19 / 60 * 2)

    def test_no_steps_for_cycling(self) -> None:
        """Cycling cadence is pedal rpm, and a step count from it would be nonsense."""
        result = parse_fit_file(make_running_fit(sport=SPORT_CYCLING), USER_ID, DS_ID)
        assert "steps_count" not in result.session

    def test_nothing_is_derived_without_a_session(self, cycling: FitParseResult) -> None:
        """An empty session keeps meaning 'the file had no rollup'."""
        assert cycling.session == {}


class TestEstimateSteps:
    _T0 = datetime(2026, 9, 19, 8, 0, 0, tzinfo=timezone.utc)

    def _series(self, *gaps: int, rate: int = 80) -> list[tuple[datetime, Decimal]]:
        points, t = [(self._T0, Decimal(rate))], self._T0
        for gap in gaps:
            t += timedelta(seconds=gap)
            points.append((t, Decimal(rate)))
        return points

    def test_integrates_over_the_real_sampling_interval(self) -> None:
        """Smart recording writes every few seconds; the time between points counts."""
        one_hz = estimate_steps(self._series(*([1] * 60)))
        every_4s = estimate_steps(self._series(*([4] * 15)))
        assert one_hz == every_4s == 160  # 80 strides/min for a minute, two feet each

    def test_a_pause_adds_no_steps(self) -> None:
        """Auto-pause writes nothing, so a long gap is stopped time.

        Integrating across it would count ten minutes of running that never happened.
        """
        with_pause = estimate_steps(self._series(*([1] * 30), 600, *([1] * 30)))
        without = estimate_steps(self._series(*([1] * 60)))
        assert with_pause == without

    def test_too_few_samples(self) -> None:
        assert estimate_steps([(self._T0, Decimal(80))]) is None
