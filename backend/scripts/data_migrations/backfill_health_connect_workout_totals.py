#!/usr/bin/env python3
"""Fill distance / energy_burned on Health Connect workouts from the records around them.

Android SDK builds before 0.12.0 sent an exercise session with a duration and nothing
else, so those workouts were stored without a distance, and with ``energy_burned = 0``
because the importer started the sum at zero. The distance was not lost: Health Connect
also syncs the app's ``DistanceRecord``s, which land in ``data_point_series`` under the
same user, provider and source app. The importer now leaves energy null when none is
sent; this brings the stored workouts in line.

The distance records are read twice by the SDK (as walking/running AND as cycling
distance), so the series are not added up. Each one is summed over the workout and the
largest total wins. Energy is the in-window active energy. A workout that had nothing
recorded gets NULL instead of 0.

Only NULL fields (and the bogus 0 kcal) are touched, so a re-run changes nothing.

Usage:
    uv run python scripts/data_migrations/backfill_health_connect_workout_totals.py --dry-run
    uv run python scripts/data_migrations/backfill_health_connect_workout_totals.py
"""

import argparse
from decimal import Decimal
from typing import Any

from sqlalchemy import Row, bindparam, text
from sqlalchemy.orm import Session

from app.database import SessionLocal

PROVIDER = "health_connect"

_DISTANCE_CODES = ("distance_walking_running", "distance_cycling", "distance_swimming", "distance_other")
_ENERGY_CODES = ("active_energy",)

_SELECT_WORKOUTS = text("""
    SELECT er.id, er.external_id, er.type, er.start_datetime, er.end_datetime,
           ds.user_id, ds.source, wd.distance, wd.energy_burned
    FROM event_record er
    JOIN data_source ds ON ds.id = er.data_source_id
    JOIN workout_details wd ON wd.record_id = er.id
    WHERE er.category = 'workout' AND ds.provider = :provider
      AND (wd.distance IS NULL OR wd.energy_burned IS NULL OR wd.energy_burned = 0)
    ORDER BY er.start_datetime DESC
""")

# Per-series totals inside the workout, from the same user, provider and source app.
# The workout and its records hang off different data_source rows (the session carries
# a device model, the records do not), so the match is on those columns, not the id.
_TOTALS = text("""
    SELECT std.code, sum(dps.value) AS total
    FROM data_point_series dps
    JOIN data_source ds ON ds.id = dps.data_source_id
    JOIN series_type_definition std ON std.id = dps.series_type_definition_id
    WHERE ds.provider = :provider AND ds.user_id = :user_id
      AND ds.source IS NOT DISTINCT FROM :source
      AND std.code IN :codes
      AND dps.is_daily_total IS NOT TRUE
      AND dps.recorded_at >= :start AND dps.recorded_at < :end
    GROUP BY std.code
""").bindparams(bindparam("codes", expanding=True))

_UPDATE = text("""
    UPDATE workout_details
    SET distance = :distance, energy_burned = :energy_burned
    WHERE record_id = :record_id
""")


def _largest_total(db: Session, row: Row[Any], codes: tuple[str, ...]) -> Decimal | None:
    params = {
        "provider": PROVIDER,
        "user_id": row.user_id,
        "source": row.source,
        "codes": codes,
        "start": row.start_datetime,
        "end": row.end_datetime,
    }
    totals = [r.total for r in db.execute(_TOTALS, params) if r.total]
    return max(totals) if totals else None


def backfill(db: Session, *, dry_run: bool) -> dict[str, int]:
    """Fill what the records allow. Does not commit; the caller owns the transaction."""
    counts = {"filled": 0, "zeroed_energy_nulled": 0, "unchanged": 0}
    rows = db.execute(_SELECT_WORKOUTS, {"provider": PROVIDER}).all()
    print(f"{len(rows)} {PROVIDER} workouts missing distance or energy\n")

    for row in rows:
        distance = row.distance
        if distance is None:
            distance = _largest_total(db, row, _DISTANCE_CODES)

        energy = row.energy_burned or None  # 0 kcal was never a measurement
        if energy is None:
            energy = _largest_total(db, row, _ENERGY_CODES)

        if distance == row.distance and energy == row.energy_burned:
            counts["unchanged"] += 1
            continue

        filled = distance != row.distance or (energy is not None and energy != row.energy_burned)
        counts["filled" if filled else "zeroed_energy_nulled"] += 1
        print(
            f"  {row.external_id} ({row.type}): distance {row.distance} -> {distance}, "
            f"energy {row.energy_burned} -> {energy}"
        )
        if not dry_run:
            db.execute(_UPDATE, {"record_id": row.id, "distance": distance, "energy_burned": energy})

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
