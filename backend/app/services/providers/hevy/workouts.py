"""Hevy workouts implementation.

Hevy has no OAuth: every request carries the user's personal API key in the
``api-key`` header (the key is stored on the connection's ``access_token``).
Sync is incremental via GET /v1/workouts/events?since=..., which returns both
'updated' (new or edited, with the full workout) and 'deleted' events — so
edits and deletions made in the Hevy app propagate on the next pull.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx
from pydantic import ValidationError

from app.constants.workout_types.hevy import get_unified_workout_type
from app.database import DbSession
from app.models import UserConnection
from app.schemas.auth import ConnectionStatus
from app.schemas.model_crud.activities import (
    EventRecordCreate,
    EventRecordDetailCreate,
    EventRecordMetrics,
)
from app.schemas.providers.hevy import HevyWorkout
from app.services.event_record_service import event_record_service
from app.services.providers.templates.base_workouts import BaseWorkoutsTemplate
from app.services.raw_payload_storage import store_raw_payload
from app.utils.structured_logging import log_structured

# Hevy caps pageSize at 10 (both /v1/workouts and /v1/workouts/events).
_PAGE_SIZE = 10
# Hard stop for the pagination loop; 1000 pages x 10 = 10k workouts per sync.
_MAX_PAGES = 1000


class HevyWorkouts(BaseWorkoutsTemplate):
    """Hevy implementation of workout syncing (API-key auth, events-feed pull)."""

    def _get_connection(self, db: DbSession, user_id: UUID) -> UserConnection:
        connection = self.connection_repo.get_by_user_and_provider(db, user_id, self.provider_name)
        if connection is None or connection.status != ConnectionStatus.ACTIVE or not connection.access_token:
            raise ValueError(f"No active Hevy connection with an API key for user {user_id}")
        return connection

    def _make_api_request(  # type: ignore[override]
        self,
        db: DbSession,
        user_id: UUID,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> Any:
        """Request with the user's stored API key; 401 marks the connection revoked.

        Bypasses make_authenticated_request: there is no Bearer token and no
        refresh flow — a rejected key can only be replaced by the user
        submitting a new one.
        """
        connection = self._get_connection(db, user_id)
        request_headers = {"api-key": connection.access_token, **(headers or {})}
        response = httpx.request(
            method,
            f"{self.api_base_url}{endpoint}",
            params=params,
            headers=request_headers,
            json=json_data,
            timeout=30.0,
        )
        if response.status_code == 401:
            # Key regenerated or Pro subscription lapsed — dead until the user reconnects.
            self.connection_repo.mark_as_revoked(db, connection)
            log_structured(
                self.logger,
                "warning",
                "Hevy API key rejected (401); connection marked revoked",
                provider=self.provider_name,
                task="api_request",
            )
        response.raise_for_status()
        result = response.json()
        store_raw_payload(
            source="api_response",
            provider=self.provider_name,
            payload=result,
            user_id=str(user_id),
            trace_id=endpoint,
        )
        return result

    def get_workout_events(
        self, db: DbSession, user_id: UUID, since: datetime
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Page through /v1/workouts/events and split into (updated workouts, deleted ids)."""
        updated: list[dict[str, Any]] = []
        deleted_ids: list[str] = []
        page = 1
        while page <= _MAX_PAGES:
            try:
                response = self._make_api_request(
                    db,
                    user_id,
                    "/v1/workouts/events",
                    params={
                        "since": since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                        "page": page,
                        "pageSize": _PAGE_SIZE,
                    },
                )
            except Exception as e:
                log_structured(
                    self.logger,
                    "error",
                    f"Error fetching Hevy workout events: {e}",
                    provider=self.provider_name,
                    task="get_workout_events",
                )
                if updated or deleted_ids:
                    log_structured(
                        self.logger,
                        "warning",
                        f"Returning partial Hevy events due to error: {e}",
                        provider=self.provider_name,
                        task="get_workout_events",
                    )
                    break
                raise
            events = response.get("events", []) if isinstance(response, dict) else []
            for event in events:
                event_type = event.get("type")
                if event_type == "updated" and isinstance(event.get("workout"), dict):
                    updated.append(event["workout"])
                elif event_type == "deleted" and event.get("id"):
                    deleted_ids.append(str(event["id"]))
            page_count = int(response.get("page_count") or 1) if isinstance(response, dict) else 1
            if page >= page_count or not events:
                break
            page += 1
        return updated, deleted_ids

    def get_workouts(self, db: DbSession, user_id: UUID, start_date: datetime, end_date: datetime) -> list[Any]:
        """Workouts updated since ``start_date`` (the events feed has no upper bound)."""
        updated, _ = self.get_workout_events(db, user_id, since=start_date)
        return updated

    def get_workouts_from_api(self, db: DbSession, user_id: UUID, **kwargs: Any) -> Any:
        page = max(int(kwargs.get("page", 1)), 1)
        page_size = min(int(kwargs.get("pageSize", kwargs.get("page_size", _PAGE_SIZE))), _PAGE_SIZE)
        return self._make_api_request(db, user_id, "/v1/workouts", params={"page": page, "pageSize": page_size})

    def get_workout_detail_from_api(self, db: DbSession, user_id: UUID, workout_id: str, **kwargs: Any) -> Any:
        return self._make_api_request(db, user_id, f"/v1/workouts/{workout_id}")

    def _normalize_workout(
        self, raw_workout: dict[str, Any], user_id: UUID
    ) -> tuple[EventRecordCreate, EventRecordDetailCreate]:
        workout = HevyWorkout.model_validate(raw_workout)
        record_id = uuid4()
        start = workout.start_time
        end = workout.end_time
        duration_seconds = max(int((end - start).total_seconds()), 0)

        metrics: EventRecordMetrics = {}
        total_distance = sum(
            s.distance_meters for ex in workout.exercises for s in ex.sets if s.distance_meters is not None
        )
        if total_distance:
            metrics["distance"] = Decimal(str(total_distance))
        # Full exercise/set structure goes into the segments JSONB so strength
        # data (reps/weights/RPE per set) survives normalization losslessly.
        segments = [ex.model_dump(mode="json", exclude_none=True) for ex in workout.exercises]

        workout_create = EventRecordCreate(
            category="workout",
            type=get_unified_workout_type(workout.title).value,
            source_name="Hevy",
            device_model=None,
            duration_seconds=duration_seconds,
            start_datetime=start,
            end_datetime=end,
            id=record_id,
            external_id=workout.id,
            source=self.provider_name,
            user_id=user_id,
        )
        detail_create = EventRecordDetailCreate(record_id=record_id, segments=segments or None, **metrics)
        return workout_create, detail_create

    def load_data(self, db: DbSession, user_id: UUID, **kwargs: Any) -> int:
        """Pull the events feed since the window start; upsert updates, apply deletes."""
        start = kwargs.get("start") or kwargs.get("start_date")
        if isinstance(start, str):
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        elif isinstance(start, datetime):
            start_dt = start
        else:
            start_dt = datetime.now(timezone.utc) - timedelta(days=30)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)

        updated, deleted_ids = self.get_workout_events(db, user_id, since=start_dt)

        count = 0
        for raw_workout in updated:
            try:
                record, detail = self._normalize_workout(raw_workout, user_id)
            except ValidationError as e:
                log_structured(
                    self.logger,
                    "error",
                    f"Skipping malformed Hevy workout: {e}",
                    provider=self.provider_name,
                    task="load_data",
                )
                continue
            created_record = event_record_service.create(db, record)
            detail_for_record = detail.model_copy(update={"record_id": created_record.id})
            event_record_service.create_detail(db, detail_for_record)
            count += 1

        for external_id in deleted_ids:
            deleted = self.workout_repo.delete_by_external_id(db, user_id, external_id, source=self.provider_name)
            if deleted:
                log_structured(
                    self.logger,
                    "info",
                    f"Deleted Hevy workout {external_id} (removed in Hevy)",
                    provider=self.provider_name,
                    task="load_data",
                )
        return count
