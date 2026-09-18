#!/usr/bin/env python3
"""Re-point Polar workouts at the UTC instant they actually happened.

Polar's exercise JSON gives a naive LOCAL ``start_time`` plus ``start_time_utc_offset``
in minutes, so UTC is local MINUS the offset. ``_extract_dates_with_offset`` added it
instead, which stored every exercise ``2 x offset`` in the future — four hours out in
summer. A workout's own FIT samples carry true UTC timestamps, so none of them fell
inside the workout they belong to.

This has to run together with the code fix, not after it: ``event_record`` dedupes on
``(data_source_id, start_datetime, end_datetime)``, not on ``external_id``. Left alone,
the next sync would compute the corrected start, find no conflicting row and insert a
SECOND copy of every exercise Polar still returns.

Idempotent by construction: the corrected value is recomputed from Polar's own JSON and
written absolutely, so a re-run is a no-op rather than another shift. Exercises Polar no
longer serves (outside its retention window) are reported and left alone — say so with
``--shift-unfetchable`` to fall back to the arithmetic, which is NOT idempotent and is
skipped for any row whose samples already line up.

Usage (with a cloud-sql-proxy running, DB_* pointed at it):
    uv run python scripts/data_migrations/fix_polar_workout_utc_offset.py --dry-run
    uv run python scripts/data_migrations/fix_polar_workout_utc_offset.py
"""

import argparse
from datetime import datetime, timedelta
from typing import Any, NamedTuple
from uuid import UUID

from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.providers.factory import ProviderFactory
from app.services.providers.polar.workouts import PolarWorkouts

PROVIDER = "polar"

_SELECT_WORKOUTS = text("""
    SELECT er.id, er.external_id, ds.user_id, er.start_datetime, er.end_datetime, er.zone_offset
    FROM event_record er
    JOIN data_source ds ON ds.id = er.data_source_id
    WHERE er.category = 'workout' AND ds.provider = :provider
    ORDER BY er.start_datetime DESC
""")

_UPDATE_TIMES = text("""
    UPDATE event_record
    SET start_datetime = :start, end_datetime = :end
    WHERE id = :id
""")

# A corrected row has its own samples inside its window; a wrong one does not.
_SAMPLES_IN_WINDOW = text("""
    SELECT count(*)
    FROM data_point_series dps
    JOIN data_source ds ON ds.id = dps.data_source_id
    WHERE ds.provider = :provider AND ds.user_id = :user_id
      AND dps.recorded_at >= :start AND dps.recorded_at < :end
""")


def _offset_minutes(zone_offset: str | None) -> int | None:
    """Parse the stored ``+02:00`` / ``-05:00`` zone offset into minutes."""
    if not zone_offset or len(zone_offset) < 6 or zone_offset[0] not in "+-":
        return None
    sign = 1 if zone_offset[0] == "+" else -1
    hours, _, minutes = zone_offset[1:].partition(":")
    if not hours.isdigit() or not minutes.isdigit():
        return None
    return sign * (int(hours) * 60 + int(minutes))


def run(*, dry_run: bool, shift_unfetchable: bool) -> dict[str, int]:
    workouts_api = ProviderFactory().get_provider(PROVIDER).workouts
    assert isinstance(workouts_api, PolarWorkouts)  # noqa: S101
    counts = {"corrected": 0, "already_correct": 0, "unfetchable": 0, "shifted": 0, "skipped": 0}

    with SessionLocal() as db:
        rows = db.execute(_SELECT_WORKOUTS, {"provider": PROVIDER}).all()
        print(f"{len(rows)} {PROVIDER} workouts\n")

        for row in rows:
            corrected = _corrected_times(workouts_api, db, row)
            if corrected is None:
                counts["unfetchable"] += 1
                if not shift_unfetchable:
                    print(f"  {row.external_id}: Polar no longer serves it — left alone")
                    continue
                corrected = _shifted_times(db, row)
                if corrected is None:
                    counts["skipped"] += 1
                    print(f"  {row.external_id}: already aligned or no offset — skipped")
                    continue
                counts["shifted"] += 1

            start, end = corrected
            if start == row.start_datetime:
                counts["already_correct"] += 1
                print(f"  {row.external_id}: already at {start} — no change")
                continue

            delta = row.start_datetime - start
            print(f"  {row.external_id}: {row.start_datetime} -> {start}  (was {delta} late)")
            if not dry_run:
                db.execute(_UPDATE_TIMES, {"id": row.id, "start": start, "end": end})
            counts["corrected"] += 1

        if dry_run:
            print("\nDry run — no changes made.")
        else:
            db.commit()

    print("\n" + "  ".join(f"{k}={v}" for k, v in counts.items()))
    return counts


class _Times(NamedTuple):
    start: datetime
    end: datetime


def _corrected_times(workouts_api: PolarWorkouts, db: Session, row: Row[Any]) -> _Times | None:
    """Recompute start/end from Polar's own JSON, or None if it no longer serves it."""
    try:
        raw = workouts_api.get_exercise_detail(db, UUID(str(row.user_id)), row.external_id)
    except Exception:
        return None
    if not raw or not raw.get("start_time"):
        return None
    start, end = workouts_api._extract_dates_with_offset(
        raw["start_time"],
        int(raw["start_time_utc_offset"]),
        raw["duration"],
    )
    tz = row.start_datetime.tzinfo
    return _Times(start.replace(tzinfo=tz), end.replace(tzinfo=tz))


def _shifted_times(db: Session, row: Row[Any]) -> _Times | None:
    """Fallback: subtract 2 x offset, unless the row's samples already line up."""
    minutes = _offset_minutes(row.zone_offset)
    if not minutes:
        return None
    in_window = db.execute(
        _SAMPLES_IN_WINDOW,
        {"provider": PROVIDER, "user_id": row.user_id, "start": row.start_datetime, "end": row.end_datetime},
    ).scalar()
    if in_window:
        return None
    shift = timedelta(minutes=2 * minutes)
    return _Times(row.start_datetime - shift, row.end_datetime - shift)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument(
        "--shift-unfetchable",
        action="store_true",
        help="Also correct exercises Polar no longer serves, by arithmetic (not idempotent)",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run, shift_unfetchable=args.shift_unfetchable)
