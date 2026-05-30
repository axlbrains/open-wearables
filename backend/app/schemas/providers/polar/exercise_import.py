from pydantic import BaseModel, Field


class HeartRateJSON(BaseModel):
    average: int | None = None
    maximum: int | None = None


class HRSamplesJSON(BaseModel):
    recording_rate: int = Field(alias="recording-rate")
    sample_type: str = Field(alias="sample-type")
    data: str


class HRZoneJSON(BaseModel):
    index: int
    lower_limit: int = Field(alias="lower-limit")
    upper_limit: int = Field(alias="upper-limit")
    in_zone: str = Field(alias="in-zone")


class RoutePointJSON(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    time: str | None = None
    satellites: int | None = None
    fix: int | None = None


class TrainingLoadProJSON(BaseModel):
    date: str | None = None
    cardio_load: int | None = Field(None, alias="cardio-load")
    muscle_load: int | None = Field(None, alias="muscle-load")
    perceived_load: int | None = Field(None, alias="perceived-load")
    cardio_load_interpretation: str | None = Field(None, alias="cardio-load-interpretation")
    muscle_load_interpretation: str | None = Field(None, alias="muscle-load-interpretation")
    perceived_load_interpretation: str | None = Field(None, alias="perceived-load-interpretation")
    user_rpe: str | None = Field(None, alias="user-rpe")


class ExerciseJSON(BaseModel):
    id: str
    upload_time: str | None = None
    polar_user: str | None = None
    # axl-api#141: Polar omits `device` for manually / phone-logged exercises,
    # which made this required field fail validation and downgrade the whole
    # workouts sync to "partial".
    device: str | None = None
    device_id: str | None = None

    sport: str
    detailed_sport_info: str | None = None

    start_time: str
    # axl-api#141: Polar may send numeric fields as floats; accept both.
    start_time_utc_offset: int | float
    duration: str

    calories: int | float | None = None
    distance: int | float | None = None
    heart_rate: HeartRateJSON | None = None
    heart_rate_zones: list[HRZoneJSON] | None = None

    training_load: float | None = None
    training_load_pro: TrainingLoadProJSON | None = None
    has_route: bool | None = None

    fat_percentage: int | None = None
    carbohydrate_percentage: int | None = None
    protein_percentage: int | None = None
    running_index: int | None = Field(None, alias="running-index")

    club_id: int | None = None
    club_name: str | None = None

    samples: list[HRSamplesJSON] | None = None
    route: list[RoutePointJSON] | None = None
