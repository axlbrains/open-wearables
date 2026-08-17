"""Tests for the delayed Strava stream-ingestion retry.

Covers the race where the activity webhook fires before Strava finishes
processing streams: the immediate fetch returns empty, and a delayed retry
task must be scheduled (and itself re-schedule with backoff until samples
land or attempts are exhausted).
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.integrations.celery.tasks.strava_stream_retry_task import (
    MAX_ATTEMPTS,
    _retry_ingest,
    retry_strava_stream_ingest,
    schedule_stream_retry,
)
from app.schemas.providers.strava import ActivityJSON as StravaActivityJSON
from app.services.providers.strava.workouts import StravaWorkouts

_ACTIVITY = StravaActivityJSON(
    id=19769960003,
    name="Evening Ride",
    type="Ride",
    sport_type="Ride",
    start_date="2026-08-16T15:39:19Z",
    elapsed_time=5800,
    utc_offset=7200.0,
    device_name="Apple Watch",
)


@pytest.fixture
def workouts() -> StravaWorkouts:
    return StravaWorkouts(
        workout_repo=MagicMock(),
        connection_repo=MagicMock(),
        provider_name="strava",
        api_base_url="https://www.strava.com",
        oauth=MagicMock(),
    )


class TestWebhookSchedulesRetry:
    def _process(self, workouts: StravaWorkouts, ingested: int, has_samples: bool) -> MagicMock:
        user_id = uuid4()
        with (
            patch("app.services.providers.strava.workouts.event_record_service") as mock_service,
            patch.object(workouts, "_ingest_workout_streams", return_value=ingested),
            patch(
                "app.services.providers.strava.workouts.timeseries_service.has_samples_in_range",
                return_value=has_samples,
            ),
            patch("app.integrations.celery.tasks.strava_stream_retry_task.schedule_stream_retry") as mock_schedule,
            patch("app.services.providers.strava.workouts.settings") as mock_settings,
        ):
            mock_settings.ingest_workout_samples = True
            mock_service.create.return_value = MagicMock(id=uuid4())
            workouts.process_push_activity(db=MagicMock(), activity=_ACTIVITY, user_id=user_id)
        return mock_schedule

    def test_empty_streams_schedule_delayed_retry(self, workouts: StravaWorkouts) -> None:
        mock_schedule = self._process(workouts, ingested=0, has_samples=False)
        mock_schedule.assert_called_once()
        args, kwargs = mock_schedule.call_args
        assert str(_ACTIVITY.id) in args or kwargs.get("activity_id") == str(_ACTIVITY.id)
        assert kwargs.get("attempt", args[-1] if args else None) == 1

    def test_no_retry_when_samples_ingested(self, workouts: StravaWorkouts) -> None:
        mock_schedule = self._process(workouts, ingested=4752, has_samples=True)
        mock_schedule.assert_not_called()

    def test_no_retry_when_samples_already_exist(self, workouts: StravaWorkouts) -> None:
        # skip-guard returned 0 because samples are already there — nothing to retry
        mock_schedule = self._process(workouts, ingested=0, has_samples=True)
        mock_schedule.assert_not_called()


class TestRetryTask:
    def _run(
        self,
        record: MagicMock | None,
        has_samples: bool,
        ingested: int,
        attempt: int,
    ) -> tuple[MagicMock, MagicMock]:
        user_id = uuid4()
        mock_workouts = MagicMock()
        mock_workouts.workout_repo.get_by_external_id.return_value = record
        mock_workouts.get_workout_detail_from_api.return_value = _ACTIVITY.model_dump() if record else None
        mock_workouts._normalize_workout.return_value = (MagicMock(), MagicMock())
        mock_workouts._ingest_workout_streams.return_value = ingested
        mock_strategy = MagicMock(workouts=mock_workouts)
        with (
            patch("app.services.providers.factory.ProviderFactory") as mock_factory,
            patch(
                "app.integrations.celery.tasks.strava_stream_retry_task.timeseries_service.has_samples_in_range",
                return_value=has_samples,
            ),
            patch("app.integrations.celery.tasks.strava_stream_retry_task.schedule_stream_retry") as mock_schedule,
        ):
            mock_factory.return_value.get_provider.return_value = mock_strategy
            _retry_ingest(MagicMock(), user_id, str(_ACTIVITY.id), attempt)
        return mock_workouts, mock_schedule

    def _record(self) -> MagicMock:
        record = MagicMock()
        record.start_datetime = _ACTIVITY.start_date
        record.end_datetime = "2026-08-16T17:15:59Z"
        return record

    def test_skips_when_samples_already_ingested(self) -> None:
        mock_workouts, mock_schedule = self._run(self._record(), has_samples=True, ingested=0, attempt=1)
        mock_workouts.get_workout_detail_from_api.assert_not_called()
        mock_schedule.assert_not_called()

    def test_ingests_when_streams_ready(self) -> None:
        mock_workouts, mock_schedule = self._run(self._record(), has_samples=False, ingested=4752, attempt=1)
        mock_workouts._ingest_workout_streams.assert_called_once()
        mock_schedule.assert_not_called()

    def test_reschedules_with_backoff_when_still_empty(self) -> None:
        _, mock_schedule = self._run(self._record(), has_samples=False, ingested=0, attempt=1)
        mock_schedule.assert_called_once()
        assert mock_schedule.call_args.args[2] == 2  # next attempt

    def test_gives_up_after_max_attempts(self) -> None:
        _, mock_schedule = self._run(self._record(), has_samples=False, ingested=0, attempt=MAX_ATTEMPTS)
        mock_schedule.assert_not_called()

    def test_gives_up_when_record_deleted(self) -> None:
        mock_workouts, mock_schedule = self._run(None, has_samples=False, ingested=0, attempt=1)
        mock_workouts.get_workout_detail_from_api.assert_not_called()
        mock_schedule.assert_not_called()


class TestTransientFailureReschedule:
    def test_task_reschedules_on_transient_error(self) -> None:
        with (
            patch(
                "app.integrations.celery.tasks.strava_stream_retry_task._retry_ingest",
                side_effect=RuntimeError("strava 500"),
            ),
            patch("app.integrations.celery.tasks.strava_stream_retry_task.SessionLocal"),
            patch(
                "app.integrations.celery.tasks.strava_stream_retry_task.schedule_stream_retry"
            ) as mock_schedule,
        ):
            retry_strava_stream_ingest(str(uuid4()), "a-1", attempt=1)
        mock_schedule.assert_called_once()
        assert mock_schedule.call_args.args[2] == 2

    def test_task_gives_up_on_transient_error_at_max_attempts(self) -> None:
        with (
            patch(
                "app.integrations.celery.tasks.strava_stream_retry_task._retry_ingest",
                side_effect=RuntimeError("strava 500"),
            ),
            patch("app.integrations.celery.tasks.strava_stream_retry_task.SessionLocal"),
            patch(
                "app.integrations.celery.tasks.strava_stream_retry_task.schedule_stream_retry"
            ) as mock_schedule,
        ):
            retry_strava_stream_ingest(str(uuid4()), "a-1", attempt=MAX_ATTEMPTS)
        mock_schedule.assert_not_called()


class TestScheduleStreamRetry:
    def test_dispatches_with_countdown_and_dedup(self) -> None:
        with patch("app.integrations.task_dispatcher.dispatch_task") as mock_dispatch:
            schedule_stream_retry("u-1", "a-1", attempt=2)
        mock_dispatch.assert_called_once()
        kwargs = mock_dispatch.call_args.kwargs
        assert kwargs["countdown"] == 900
        assert kwargs["dedup_key"] == "strava_streams:u-1:a-1:2"
        assert kwargs["kwargs"]["attempt"] == 2
