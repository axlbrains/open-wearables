"""Delayed retry for Strava per-sample stream ingestion.

Strava fires the activity webhook seconds after upload, before stream
processing on their side has finished — the immediate /streams fetch in the
webhook path then comes back empty and the workout is saved without samples.
The hourly pull can't repair it either: the webhook bumps last_synced_at past
the activity's start time, so the pull window never re-covers the workout.

This task re-fetches the streams a few minutes later, when Strava has
finished processing. It is idempotent (skips if samples already exist) and
self-limits to MAX_ATTEMPTS.
"""

from logging import getLogger
from uuid import UUID

from celery import shared_task

from app.database import DbSession, SessionLocal
from app.schemas.providers.strava import ActivityJSON as StravaActivityJSON
from app.services.providers.factory import ProviderFactory
from app.services.timeseries_service import timeseries_service
from app.utils.sentry_helpers import log_and_capture_error
from app.utils.structured_logging import log_structured

logger = getLogger(__name__)

MAX_ATTEMPTS = 3
# Backoff between attempts, seconds: webhook +5min, then +15min, then +45min.
RETRY_COUNTDOWNS = {1: 300, 2: 900, 3: 2700}


@shared_task
def retry_strava_stream_ingest(user_id: str, activity_id: str, attempt: int = 1) -> None:
    """Fetch and persist streams for an already-saved Strava workout."""
    try:
        with SessionLocal() as db:
            _retry_ingest(db, UUID(user_id), str(activity_id), attempt)
    except Exception as e:
        log_and_capture_error(e, logger, "Strava stream retry failed", extra={"activity_id": activity_id})


def _retry_ingest(db: DbSession, user_uuid: UUID, activity_id: str, attempt: int) -> None:
    workouts = ProviderFactory().get_provider("strava").workouts
    record = workouts.workout_repo.get_by_external_id(db, user_uuid, activity_id, source="strava")
    if record is None:
        log_structured(
            logger,
            "warning",
            "Strava stream retry: workout no longer exists, giving up",
            provider="strava",
            action="stream_retry_no_record",
            activity_id=activity_id,
        )
        return

    if record.end_datetime is not None and timeseries_service.has_samples_in_range(
        db, user_uuid, "strava", record.start_datetime, record.end_datetime
    ):
        log_structured(
            logger,
            "info",
            "Strava stream retry: samples already ingested, nothing to do",
            provider="strava",
            action="stream_retry_already_done",
            activity_id=activity_id,
        )
        return

    activity_data = workouts.get_workout_detail_from_api(db, user_uuid, activity_id)
    ingested = 0
    if activity_data:
        activity = StravaActivityJSON(**activity_data)
        record_create, _ = workouts._normalize_workout(activity, user_uuid)
        ingested = workouts._ingest_workout_streams(db, activity, user_uuid, record_create)

    if ingested > 0:
        db.commit()
        log_structured(
            logger,
            "info",
            "Strava stream retry: ingested samples",
            provider="strava",
            action="stream_retry_success",
            activity_id=activity_id,
            sample_count=ingested,
            attempt=attempt,
        )
        return

    if attempt >= MAX_ATTEMPTS:
        log_structured(
            logger,
            "warning",
            "Strava stream retry: still no streams after final attempt, giving up",
            provider="strava",
            action="stream_retry_exhausted",
            activity_id=activity_id,
            attempt=attempt,
        )
        return

    schedule_stream_retry(str(user_uuid), activity_id, attempt + 1)


def schedule_stream_retry(user_id: str, activity_id: str, attempt: int) -> None:
    """Schedule a (re)try with the attempt's backoff."""
    countdown = RETRY_COUNTDOWNS.get(attempt, RETRY_COUNTDOWNS[MAX_ATTEMPTS])
    retry_strava_stream_ingest.apply_async(
        kwargs={"user_id": user_id, "activity_id": activity_id, "attempt": attempt},
        countdown=countdown,
    )
    log_structured(
        logger,
        "info",
        "Strava streams not ready; scheduled delayed ingest",
        provider="strava",
        action="stream_retry_scheduled",
        activity_id=activity_id,
        attempt=attempt,
        countdown_seconds=countdown,
    )
