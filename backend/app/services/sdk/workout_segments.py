"""Moving time from a Health Connect exercise session's segments.

A Health Connect session spans from start to stop, pauses included, so its
``endDate - startDate`` is elapsed time, not the time the athlete was moving. The
session's segments say which parts were which. The Android SDK sends each one as
``{"startDate", "endDate", "type"}``, where ``type`` is a name for the segment kinds
it knows ("running", "rest", ...) and ``other_<n>`` for the rest; a pause is
``other_39`` (``ExerciseSegment.EXERCISE_SEGMENT_TYPE_PAUSE``).
"""

from datetime import datetime
from typing import Any

# Segment types during which the athlete is not moving.
_IDLE_TYPES = frozenset({"rest", "pause", "other_39"})


def _seconds(segment: dict[str, Any]) -> float | None:
    try:
        start = datetime.fromisoformat(str(segment["startDate"]))
        end = datetime.fromisoformat(str(segment["endDate"]))
    except (KeyError, TypeError, ValueError):
        return None
    seconds = (end - start).total_seconds()
    return seconds if seconds > 0 else None


def health_connect_moving_time(segments: list[dict[str, Any]] | None, duration_seconds: int) -> int | None:
    """Seconds spent moving, or None when the segments do not say.

    Active segments are summed when there are any: an app that marks only the running
    part of a session (Fitbit does) leaves the rest of it unsegmented, and that part is
    not movement either. A session segmented only into pauses and rests is the other
    way round, so those are subtracted from the elapsed time instead.
    """
    if not segments:
        return None

    active = idle = 0.0
    for segment in segments:
        seconds = _seconds(segment)
        if seconds is None:
            continue
        if str(segment.get("type", "")).lower() in _IDLE_TYPES:
            idle += seconds
        else:
            active += seconds

    if active:
        moving = active
    elif idle:
        moving = duration_seconds - idle
    else:
        return None
    return max(0, min(int(round(moving)), duration_seconds))
