from app.schemas.enums import SeriesType
from app.schemas.enums.health_score_category import HealthScoreCategory

# Daily-activity mapping (DailyActivityJSON attribute → SeriesType) consumed
# directly by data_247.normalize_daily_activity via /v3/users/activities.
ACTIVITY_SERIES: dict[str, SeriesType] = {
    "steps": SeriesType.steps,
    "active_calories": SeriesType.active_energy,
    "distance_from_steps": SeriesType.distance_walking_running,
    "active_time_minutes": SeriesType.active_time,
}

# Per-sample series recorded by the watch. Polar's exercise JSON has no samples at
# all -- /v3/exercises/{id}/samples is 404 on AccessLink -- so these come from the
# exercise's FIT file, parsed by the shared fit_parser.
FIT_WORKOUT_SERIES: frozenset[SeriesType] = frozenset(
    {
        SeriesType.heart_rate,
        SeriesType.speed,
        SeriesType.cadence,
        SeriesType.power,
        SeriesType.elevation,
        SeriesType.latitude,
        SeriesType.longitude,
        SeriesType.air_temperature,
        SeriesType.running_vertical_oscillation,
        SeriesType.running_ground_contact_time,
        SeriesType.running_stride_length,
        SeriesType.running_vertical_ratio,
        SeriesType.running_stance_time_balance,
    }
)

TIMESERIES: frozenset[SeriesType] = frozenset(
    {
        *ACTIVITY_SERIES.values(),  # /v3/users/activities
        SeriesType.heart_rate,  # /v3/users/sleep + /v3/users/continuous-heart-rate + /v3/users/wrist-ecg
        SeriesType.heart_rate_variability_rmssd,  # /v3/users/spo2 + /v3/users/wrist-ecg
        SeriesType.oxygen_saturation,  # /v3/users/spo2
        SeriesType.skin_temperature,  # /v3/users/sleep-skin-temperature + /v3/users/body-temperature (SKIN)
        SeriesType.skin_temperature_deviation,  # /v3/users/sleep-skin-temperature (deviation_from_baseline)
        SeriesType.body_temperature,  # /v3/users/body-temperature (CORE)
        *FIT_WORKOUT_SERIES,  # /v3/exercises/{id}/fit
    }
)

# EventRecordDetail fields populated by workouts.py (workout records).
# The first four come from the /v3/exercises JSON; the rest are rolled up from the
# exercise's FIT session message and laps.
WORKOUT_FIELDS: frozenset[str] = frozenset(
    {
        "heart_rate_max",
        "heart_rate_avg",
        "energy_burned",
        "distance",
        "steps_count",
        "moving_time_seconds",
        "average_speed",
        "max_speed",
        "average_cadence",
        "average_watts",
        "max_watts",
        "total_elevation_gain",
        "elev_high",
        "elev_low",
        "segments",
        "hr_zones",
        "power_zones",
    }
)

# EventRecordDetail fields populated by data_247.py (sleep records)
SLEEP_FIELDS: frozenset[str] = frozenset(
    {
        "sleep_total_duration_minutes",
        "sleep_time_in_bed_minutes",
        "sleep_deep_minutes",
        "sleep_rem_minutes",
        "sleep_light_minutes",
        "sleep_awake_minutes",
        "sleep_stages",
    }
)

HEALTH_SCORES: frozenset[HealthScoreCategory] = frozenset(
    {
        HealthScoreCategory.SLEEP,
        HealthScoreCategory.STRAIN,
        HealthScoreCategory.RECOVERY,
        HealthScoreCategory.READINESS,
    }
)
