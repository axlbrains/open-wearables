import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable
from uuid import UUID, uuid4

import httpx
import isodate
from fastapi import HTTPException, status
from pydantic import ValidationError

from app.config import settings
from app.constants.workout_types.polar import get_unified_workout_type
from app.database import DbSession
from app.schemas.model_crud.activities import (
    EventRecordCreate,
    EventRecordDetailCreate,
    EventRecordMetrics,
    TimeSeriesSampleCreate,
)
from app.schemas.providers.polar import ExerciseJSON as PolarExerciseJSON
from app.services.event_record_service import event_record_service
from app.services.fit_parser import parse_fit_file
from app.services.providers.api_client import download_binary_content
from app.services.providers.templates.base_workouts import BaseWorkoutsTemplate
from app.services.timeseries_service import timeseries_service
from app.utils.dates import offset_to_iso
from app.utils.sentry_helpers import log_and_capture_error
from app.utils.structured_logging import log_structured

logger = logging.getLogger(__name__)


class PolarWorkouts(BaseWorkoutsTemplate):
    """Polar implementation of workouts template."""

    def get_workouts(
        self,
        db: DbSession,
        user_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> list[Any]:
        """Get exercises from Polar API."""
        return self._make_api_request(db, user_id, "/v3/exercises")

    def get_workouts_from_api(self, db: DbSession, user_id: UUID, **kwargs: Any) -> Any:
        """Get exercises from Polar API with options."""
        samples = kwargs.get("samples", False)
        zones = kwargs.get("zones", False)
        route = kwargs.get("route", False)

        params = {
            "samples": str(samples).lower(),
            "zones": str(zones).lower(),
            "route": str(route).lower(),
        }
        return self._make_api_request(db, user_id, "/v3/exercises", params=params)

    def get_workout_detail_from_api(self, db: DbSession, user_id: UUID, workout_id: str, **kwargs: Any) -> Any:
        """Get detailed exercise data from Polar API."""
        samples = kwargs.get("samples", False)
        zones = kwargs.get("zones", False)
        route = kwargs.get("route", False)
        return self.get_exercise_detail(db, user_id, workout_id, samples, zones, route)

    def _extract_dates(self, start_timestamp: Any, end_timestamp: Any) -> tuple[datetime, datetime]:
        """Extract start and end dates from timestamps.

        Note: Polar uses a different format with offset, so this delegates to _extract_dates_with_offset.
        This is required by the base template but not used directly.
        """
        raise NotImplementedError("Use _extract_dates_with_offset for Polar workouts")

    def _extract_dates_with_offset(
        self,
        start_time: str,
        start_time_utc_offset: int,
        duration: str,
    ) -> tuple[datetime, datetime]:
        """Extract start and end dates from timestamps with UTC offset."""
        start_date = isodate.parse_datetime(start_time)
        offset = timedelta(minutes=start_time_utc_offset)
        start_date = start_date + offset
        duration_td = isodate.parse_duration(duration)
        end_date = start_date + duration_td
        return start_date, end_date

    def _build_metrics(self, raw_workout: PolarExerciseJSON) -> EventRecordMetrics:
        hr_avg = (
            Decimal(str(raw_workout.heart_rate.average))
            if raw_workout.heart_rate and raw_workout.heart_rate.average is not None
            else None
        )
        hr_max = (
            Decimal(str(raw_workout.heart_rate.maximum))
            if raw_workout.heart_rate and raw_workout.heart_rate.maximum is not None
            else None
        )

        energy_burned = Decimal(str(raw_workout.calories)) if raw_workout.calories is not None else None

        distance = Decimal(str(raw_workout.distance)) if raw_workout.distance is not None else None

        return {
            "heart_rate_max": int(hr_max) if hr_max is not None else None,
            "heart_rate_avg": hr_avg,
            "energy_burned": energy_burned,
            "distance": distance,
        }

    def _normalize_workout(
        self,
        raw_workout: PolarExerciseJSON,
        user_id: UUID,
    ) -> tuple[EventRecordCreate, EventRecordDetailCreate]:
        """Normalize Polar exercise to EventRecordCreate and EventRecordDetailCreate."""
        workout_id = uuid4()

        workout_type = get_unified_workout_type(raw_workout.sport, raw_workout.detailed_sport_info)

        # axl-api#141: Polar may send the offset as a float; normalize to int once
        # for the int-typed downstream helpers (and offset_to_iso's `{:02d}` formatting).
        start_offset_minutes = int(raw_workout.start_time_utc_offset)

        start_date, end_date = self._extract_dates_with_offset(
            raw_workout.start_time,
            start_offset_minutes,
            raw_workout.duration,
        )
        duration_seconds = int((end_date - start_date).total_seconds())

        metrics = self._build_metrics(raw_workout)

        # convert from offset minutes to seconds first
        zone_offset = offset_to_iso(start_offset_minutes * 60)

        record = EventRecordCreate(
            category="workout",
            type=workout_type.value,
            # axl-api#141: `device` is optional now (Polar omits it for phone-logged
            # exercises); fall back to the provider name for the required source_name.
            source_name=raw_workout.device or "polar",
            device_model=raw_workout.device,
            duration_seconds=duration_seconds,
            start_datetime=start_date,
            end_datetime=end_date,
            zone_offset=zone_offset,
            id=workout_id,
            external_id=raw_workout.id,
            source="polar",
            user_id=user_id,
        )

        detail = EventRecordDetailCreate(
            record_id=workout_id,
            **metrics,
        )

        return record, detail

    def _parse_exercises(
        self,
        raw_exercises: Iterable[dict[str, Any]],
        user_id: UUID,
    ) -> list[PolarExerciseJSON]:
        """Validate raw Polar exercises, skipping (not failing on) malformed ones.

        axl-api#141: a single exercise that fails ``ExerciseJSON`` validation
        used to raise and downgrade the whole workouts sync to "partial" with
        zero workouts saved. We now log and skip the offending exercise so the
        remaining valid exercises still import.
        """
        parsed: list[PolarExerciseJSON] = []
        for raw_exercise in raw_exercises:
            try:
                parsed.append(PolarExerciseJSON(**raw_exercise))
            except ValidationError as exc:
                logger.warning(
                    "Skipping malformed Polar exercise",
                    extra={
                        "action": "polar_workout_partial_data",
                        "user_id": str(user_id),
                        "exercise_id": raw_exercise.get("id") if isinstance(raw_exercise, dict) else None,
                        "errors": exc.errors(include_url=False),
                    },
                )
        return parsed

    def _build_bundles(
        self,
        raw: list[PolarExerciseJSON],
        user_id: UUID,
    ) -> Iterable[tuple[PolarExerciseJSON, EventRecordCreate, EventRecordDetailCreate]]:
        """Build event record payloads for Polar exercises, paired with their source JSON."""
        for raw_workout in raw:
            record, detail = self._normalize_workout(raw_workout, user_id)
            yield raw_workout, record, detail

    def _save_bundles(
        self,
        db: DbSession,
        user_id: UUID,
        bundles: Iterable[tuple[PolarExerciseJSON, EventRecordCreate, EventRecordDetailCreate]],
    ) -> int:
        """Persist each exercise, enriching its detail from the FIT file first."""
        count = 0
        for raw_workout, record, detail in bundles:
            self._ingest_fit(db, user_id, raw_workout, record, detail)
            created_record = event_record_service.create(db, record)
            event_record_service.create_detail(db, detail.model_copy(update={"record_id": created_record.id}))
            count += 1
        return count

    def load_data(
        self,
        db: DbSession,
        user_id: UUID,
        **kwargs: Any,
    ) -> int:
        """Load data from Polar API."""
        workouts_data = self.get_workouts_from_api(db, user_id, **kwargs)
        workouts = self._parse_exercises(workouts_data, user_id)
        return self._save_bundles(db, user_id, self._build_bundles(workouts, user_id))

    def fetch_and_save_exercise(self, db: DbSession, user_id: UUID, path: str) -> int:
        """Fetch a single exercise by URL path and save it. Used by webhook handler."""
        raw = self._make_api_request(db, user_id, path)
        if not raw:
            return 0
        return self._save_bundles(db, user_id, self._build_bundles(self._parse_exercises([raw], user_id), user_id))

    def _fit_already_ingested(self, db: DbSession, user_id: UUID, exercise_id: str) -> bool:
        """Whether this exercise's FIT file was already folded into the stored workout.

        Every FIT ``session`` message carries ``total_timer_time`` and the Polar exercise
        JSON has no equivalent, so ``moving_time_seconds`` is the marker that the file was
        parsed. Exercises are re-upserted on every sync window that re-covers them, and the
        FIT is immutable once uploaded, so without this probe each re-cover would re-download
        a file we already have. Workouts imported before FIT support get enriched on their
        next re-cover, which is what backfills them.
        """
        existing = self.workout_repo.get_by_external_id(db, user_id, exercise_id, provider=self.provider_name)
        return bool(existing and existing.workout_detail and existing.workout_detail.moving_time_seconds is not None)

    def _fetch_fit(self, db: DbSession, user_id: UUID, exercise_id: str) -> bytes | None:
        """Download an exercise's FIT file, or None when Polar has none for it."""
        try:
            return download_binary_content(
                db,
                user_id,
                self.connection_repo,
                self.oauth,
                self.provider_name,
                f"{self.api_base_url}/v3/exercises/{exercise_id}/fit",
            )
        except (httpx.HTTPStatusError, HTTPException) as exc:
            # download_binary_content surfaces the provider status through
            # response.raise_for_status(), i.e. httpx.HTTPStatusError -- not the
            # fastapi HTTPException the JSON paths raise. Both are matched so the
            # quiet branch cannot go dead again if the helper changes.
            code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else exc.status_code
            if code in (status.HTTP_204_NO_CONTENT, status.HTTP_404_NOT_FOUND):
                # Phone-logged and manually entered exercises have no recorded file.
                # A permanent property of the exercise, so this stays quiet rather than
                # re-reporting on every sync window that re-covers it.
                log_structured(
                    self.logger,
                    "info",
                    "Polar exercise has no FIT file; keeping JSON metrics only",
                    provider="polar",
                    action="polar_fit_absent",
                    exercise_id=exercise_id,
                    user_id=str(user_id),
                )
                return None
            log_and_capture_error(
                exc,
                self.logger,
                "Failed to download Polar FIT file, keeping JSON metrics only",
                extra={"exercise_id": exercise_id},
            )
            return None
        except Exception as exc:
            log_and_capture_error(
                exc,
                self.logger,
                "Failed to download Polar FIT file, keeping JSON metrics only",
                extra={"exercise_id": exercise_id},
            )
            return None

    def _ingest_fit(
        self,
        db: DbSession,
        user_id: UUID,
        raw_workout: PolarExerciseJSON,
        record: EventRecordCreate,
        detail: EventRecordDetailCreate,
    ) -> int:
        """Fold an exercise's FIT file into its detail and persist its per-sample series.

        Polar's ``/v3/exercises`` JSON carries four metrics (avg/max HR, calories,
        distance); everything else the watch recorded — speed, cadence, power, altitude,
        GPS, laps — only exists in the FIT file. Failure-isolated: the workout still saves
        with its JSON metrics if any part of this fails.

        Returns the number of samples written.
        """
        if self._fit_already_ingested(db, user_id, raw_workout.id):
            return 0

        fit_bytes = self._fetch_fit(db, user_id, raw_workout.id)
        if not fit_bytes:
            return 0

        try:
            parsed = parse_fit_file(fit_bytes, user_id, source=self.provider_name)
        except Exception as exc:
            log_and_capture_error(
                exc,
                self.logger,
                "Failed to parse Polar FIT file, keeping JSON metrics only",
                extra={"exercise_id": raw_workout.id},
            )
            return 0

        # The JSON is the provider's own rollup, so it wins where the two overlap;
        # the FIT only fills what Polar left out.
        for key, value in parsed.session.items():
            if getattr(detail, key, None) is None:
                setattr(detail, key, value)
        if parsed.segments:
            detail.segments = parsed.segments
        if parsed.hr_zones:
            detail.hr_zones = parsed.hr_zones
        if parsed.power_zones:
            detail.power_zones = parsed.power_zones

        samples: list[TimeSeriesSampleCreate] = []
        if settings.ingest_workout_samples and parsed.samples:
            for sample in parsed.samples:
                sample.zone_offset = record.zone_offset
                sample.device_model = record.device_model
            samples = parsed.samples
            # Savepoint so a failed bulk insert rolls back only the samples and leaves
            # the workout's outer transaction usable (no PendingRollbackError).
            nested = db.begin_nested()
            try:
                timeseries_service.bulk_create_samples(db, samples)
                nested.commit()
            except Exception as exc:
                nested.rollback()
                log_and_capture_error(
                    exc,
                    self.logger,
                    "Polar FIT sample ingestion failed; workout still saved",
                    extra={"exercise_id": raw_workout.id, "sample_count": len(samples)},
                )
                samples = []

        log_structured(
            self.logger,
            "info",
            "Parsed Polar FIT file",
            provider="polar",
            action="polar_fit_ingested",
            exercise_id=raw_workout.id,
            user_id=str(user_id),
            segments=len(parsed.segments),
            samples=len(samples),
            session_fields=sorted(parsed.session),
        )
        return len(samples)

    def get_exercise_detail(
        self,
        db: DbSession,
        user_id: UUID,
        exercise_id: str,
        samples: bool = False,
        zones: bool = False,
        route: bool = False,
    ) -> dict:
        """Get detailed exercise data from Polar API."""
        params = {
            "samples": str(samples).lower(),
            "zones": str(zones).lower(),
            "route": str(route).lower(),
        }
        return self._make_api_request(db, user_id, f"/v3/exercises/{exercise_id}", params=params)
