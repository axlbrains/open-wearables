#!/usr/bin/env python3
"""Fill elev_high / elev_low / steps_count on Polar workouts from their stored samples.

Polar's FIT files record altitude and cadence on every record but put neither the
altitude span nor a step total in the session. The parser now derives both from the
samples (see ``_fill_session_from_samples`` in ``app/services/fit_parser.py``), but
workouts already ingested will not re-parse their FIT: the skip guard carries their
stored FIT fields forward instead. This computes the same values from the samples
already in ``data_point_series``, so it needs no calls to Polar.

Only NULL fields are filled, so a device's own figure is never overwritten and a
re-run changes nothing. A workout whose samples do not fall inside its window (one
stored before the UTC-offset fix and never corrected) gets nothing, which is right:
its samples belong to a different time.

Usage:
    uv run python scripts/data_migrations/backfill_polar_fit_derived_fields.py --dry-run
    uv run python scripts/data_migrations/backfill_polar_fit_derived_fields.py
"""

import argparse
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.fit_parser import elevation_range, estimate_steps

PROVIDER = "polar"

# Unified workout types whose FIT cadence counts one foot, so steps are derivable.
# The live path decides on the FIT sport instead; this is the stored equivalent.
_ON_FOOT_TYPES = (
    "running",
    "trail_running",
    "treadmill",
    "walking",
    "walking_fitness",
    "hiking",
    "mountaineering",
    "orienteering",
)

_SELECT_WORKOUTS = text("""
    SELECT er.id, er.external_id, er.type, er.start_datetime, er.end_datetime, ds.user_id,
           wd.elev_high, wd.elev_low, wd.steps_count
    FROM event_record er
    JOIN data_source ds ON ds.id = er.data_source_id
    JOIN workout_details wd ON wd.record_id = er.id
    WHERE er.category = 'workout' AND ds.provider = :provider
      AND (wd.elev_high IS NULL OR wd.elev_low IS NULL OR wd.steps_count IS NULL)
    ORDER BY er.start_datetime DESC
""")

# The workout's own samples: same user, same provider, inside its window.
_SAMPLES = text("""
    SELECT dps.recorded_at, dps.value
    FROM data_point_series dps
    JOIN data_source ds ON ds.id = dps.data_source_id
    JOIN series_type_definition std ON std.id = dps.series_type_definition_id
    WHERE ds.provider = :provider AND ds.user_id = :user_id AND std.code = :code
      AND dps.recorded_at >= :start AND dps.recorded_at < :end
    ORDER BY dps.recorded_at
""")

_UPDATE = text("""
    UPDATE workout_details
    SET elev_high = COALESCE(elev_high, :elev_high),
        elev_low = COALESCE(elev_low, :elev_low),
        steps_count = COALESCE(steps_count, :steps_count)
    WHERE record_id = :record_id
""")


def _samples(db: Session, row: Row[Any], code: str) -> list[tuple[Any, Any]]:
    params = {
        "provider": PROVIDER,
        "user_id": row.user_id,
        "code": code,
        "start": row.start_datetime,
        "end": row.end_datetime,
    }
    return [(r.recorded_at, r.value) for r in db.execute(_SAMPLES, params)]


def backfill(db: Session, *, dry_run: bool) -> dict[str, int]:
    """Fill the derivable fields. Does not commit; the caller owns the transaction."""
    counts = {"filled": 0, "nothing_to_fill": 0}
    rows = db.execute(_SELECT_WORKOUTS, {"provider": PROVIDER}).all()
    print(f"{len(rows)} {PROVIDER} workouts missing at least one field\n")

    for row in rows:
        span = elevation_range([value for _, value in _samples(db, row, "elevation")])
        steps = estimate_steps(_samples(db, row, "cadence")) if row.type in _ON_FOOT_TYPES else None

        # Only what is still empty AND derivable counts. A re-run finds rows that still
        # miss a field it cannot fill (no cadence, say), and must not report them again.
        values: dict[str, Any] = {"elev_low": None, "elev_high": None, "steps_count": None}
        if span and row.elev_low is None:
            values["elev_low"] = span[0]
        if span and row.elev_high is None:
            values["elev_high"] = span[1]
        if steps and row.steps_count is None:
            values["steps_count"] = steps
        if all(v is None for v in values.values()):
            counts["nothing_to_fill"] += 1
            continue

        filled = ", ".join(f"{k}={v}" for k, v in values.items() if v is not None)
        print(f"  {row.external_id} ({row.type}): {filled}")
        if not dry_run:
            db.execute(_UPDATE, {"record_id": row.id, **values})
        counts["filled"] += 1

    print("\n" + "  ".join(f"{k}={v}" for k, v in counts.items()))
    return counts


def main(*, dry_run: bool) -> None:
    with SessionLocal() as db:
        backfill(db, dry_run=dry_run)
        if dry_run:
            print("Dry run, no changes made.")
            return
        db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    main(dry_run=parser.parse_args().dry_run)
