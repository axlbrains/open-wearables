"""
Tests for Polar workouts implementation.

Tests the PolarWorkouts class for fetching and processing workout data from Polar API.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.constants.workout_types.polar import get_unified_workout_type
from app.schemas.enums import WorkoutType
from app.schemas.providers.polar import ExerciseJSON as PolarExerciseJSON
from app.services.providers.polar.workouts import PolarWorkouts
from tests.factories import UserConnectionFactory, UserFactory


class TestPolarWorkoutsInitialization:
    """Tests for PolarWorkouts initialization."""

    def test_polar_workouts_initialization(self, db: Session) -> None:
        """Test PolarWorkouts initializes with required dependencies."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )

        # Act
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        # Assert
        assert workouts is not None
        assert workouts.provider_name == "polar"
        assert workouts.api_base_url == "https://www.polaraccesslink.com"
        assert workouts.oauth is oauth


class TestPolarWorkoutsDateExtraction:
    """Tests for Polar-specific date extraction with UTC offset."""

    def test_extract_dates_with_offset_positive_offset(self, db: Session) -> None:
        """Test extracting dates with positive UTC offset."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        # Act
        start_date, end_date = workouts._extract_dates_with_offset(
            start_time="2024-01-15T08:00:00",
            start_time_utc_offset=60,  # +1 hour
            duration="PT1H0M0S",  # 1 hour
        )

        # Assert
        assert isinstance(start_date, datetime)
        assert isinstance(end_date, datetime)
        assert end_date > start_date
        assert (end_date - start_date).total_seconds() == 3600  # 1 hour

    def test_extract_dates_with_offset_negative_offset(self, db: Session) -> None:
        """Test extracting dates with negative UTC offset."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        # Act
        start_date, end_date = workouts._extract_dates_with_offset(
            start_time="2024-01-15T08:00:00",
            start_time_utc_offset=-300,  # -5 hours
            duration="PT30M0S",  # 30 minutes
        )

        # Assert
        assert isinstance(start_date, datetime)
        assert isinstance(end_date, datetime)
        assert (end_date - start_date).total_seconds() == 1800  # 30 minutes

    def test_extract_dates_not_implemented_fallback(self, db: Session) -> None:
        """Test that _extract_dates raises NotImplementedError for Polar."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        # Act & Assert
        with pytest.raises(NotImplementedError):
            workouts._extract_dates("2024-01-15T08:00:00", "2024-01-15T09:00:00")


class TestPolarWorkoutsMetricsBuilding:
    """Tests for building metrics from Polar exercise data."""

    def test_build_metrics_with_heart_rate_data(self, db: Session, sample_polar_exercise: dict) -> None:
        """Test building metrics with complete heart rate data."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        exercise = PolarExerciseJSON(**sample_polar_exercise)

        # Act
        metrics = workouts._build_metrics(exercise)

        # Assert
        assert metrics["heart_rate_avg"] == Decimal("145")
        assert metrics["heart_rate_max"] == 175
        assert metrics["energy_burned"] == Decimal("650")
        assert metrics["distance"] == Decimal("10000")

    def test_build_metrics_without_heart_rate_data(self, db: Session) -> None:
        """Test building metrics when heart rate data is missing."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        exercise = PolarExerciseJSON(
            id="ABC123",
            device="Polar Vantage V2",
            start_time="2024-01-15T08:00:00",
            start_time_utc_offset=60,
            duration="PT1H0M0S",
            sport="RUNNING",
            detailed_sport_info="RUNNING",
        )

        # Act
        metrics = workouts._build_metrics(exercise)

        # Assert
        assert metrics["heart_rate_avg"] is None
        assert metrics["heart_rate_max"] is None


class TestPolarWorkoutsNormalization:
    """Tests for normalizing Polar exercises to event records."""

    def test_normalize_workout_complete_data(self, db: Session, sample_polar_exercise: dict) -> None:
        """Test normalizing workout with complete data."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user = UserFactory()
        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        exercise = PolarExerciseJSON(**sample_polar_exercise)

        # Act
        record, detail = workouts._normalize_workout(exercise, user.id)

        # Assert
        assert record.category == "workout"
        assert record.type == WorkoutType.RUNNING.value
        assert record.source_name == "Polar Vantage V2"
        assert record.device_model == "Polar Vantage V2"
        assert record.duration_seconds == 3600
        assert record.external_id == "ABC123"
        assert record.user_id == user.id
        assert detail.heart_rate_avg == Decimal("145")
        assert detail.heart_rate_max == 175

    def test_normalize_workout_workout_type_mapping(self, db: Session) -> None:
        """Test workout type is correctly mapped from Polar sport type."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user = UserFactory()
        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        # Test cycling
        exercise = PolarExerciseJSON(
            id="CYC123",
            device="Polar Vantage V2",
            start_time="2024-01-15T08:00:00",
            start_time_utc_offset=60,
            duration="PT1H0M0S",
            sport="CYCLING",
            detailed_sport_info="CYCLING_ROAD",
        )

        # Act
        record, detail = workouts._normalize_workout(exercise, user.id)

        # Assert
        assert record.type == WorkoutType.CYCLING.value


class TestPolarWorkoutsAPIRequests:
    """Tests for API request methods."""

    @patch("app.services.providers.templates.base_workouts.make_authenticated_request")
    def test_get_workouts_from_api_default_params(self, mock_request: MagicMock, db: Session) -> None:
        """Test getting workouts with default parameters."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")

        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        mock_request.return_value = []

        # Act
        workouts.get_workouts_from_api(db, user.id)

        # Assert
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["endpoint"] == "/v3/exercises"
        assert call_kwargs["params"]["samples"] == "false"
        assert call_kwargs["params"]["zones"] == "false"
        assert call_kwargs["params"]["route"] == "false"

    @patch("app.services.providers.templates.base_workouts.make_authenticated_request")
    def test_get_workouts_from_api_with_options(self, mock_request: MagicMock, db: Session) -> None:
        """Test getting workouts with samples, zones, and route enabled."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")

        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        mock_request.return_value = []

        # Act
        workouts.get_workouts_from_api(db, user.id, samples=True, zones=True, route=True)

        # Assert
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert call_kwargs["params"]["samples"] == "true"
        assert call_kwargs["params"]["zones"] == "true"
        assert call_kwargs["params"]["route"] == "true"

    @patch("app.services.providers.templates.base_workouts.make_authenticated_request")
    def test_get_workout_detail_from_api(self, mock_request: MagicMock, db: Session) -> None:
        """Test getting detailed workout data for specific exercise."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")

        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        mock_request.return_value = {}
        workout_id = "ABC123"

        # Act
        workouts.get_workout_detail_from_api(db, user.id, workout_id, samples=True)

        # Assert
        mock_request.assert_called_once()
        call_kwargs = mock_request.call_args[1]
        assert f"/v3/exercises/{workout_id}" in call_kwargs["endpoint"]
        assert call_kwargs["params"]["samples"] == "true"


class TestPolarWorkoutsDataLoading:
    """Tests for loading workout data from Polar API."""

    @patch("app.services.providers.templates.base_workouts.make_authenticated_request")
    @patch("app.services.event_record_service.event_record_service.create")
    @patch("app.services.event_record_service.event_record_service.create_detail")
    def test_load_data_success(
        self,
        mock_create_detail: MagicMock,
        mock_create: MagicMock,
        mock_request: MagicMock,
        db: Session,
        sample_polar_exercise: dict,
    ) -> None:
        """Test successful data loading from Polar API."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")

        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        mock_request.return_value = [sample_polar_exercise]

        # Act
        result = workouts.load_data(db, user.id)

        # Assert
        assert result == 1
        mock_create.assert_called_once()
        mock_create_detail.assert_called_once()

    @patch("app.services.providers.templates.base_workouts.make_authenticated_request")
    def test_load_data_empty_response(self, mock_request: MagicMock, db: Session) -> None:
        """Test loading data when API returns empty list."""
        # Arrange
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")

        user_repo = UserRepository(User)
        connection_repo = UserConnectionRepository()
        workout_repo = EventRecordRepository(EventRecord)
        oauth = PolarOAuth(
            user_repo=user_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
        )
        workouts = PolarWorkouts(
            workout_repo=workout_repo,
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=oauth,
        )

        mock_request.return_value = []

        # Act
        result = workouts.load_data(db, user.id)

        # Assert
        assert result == 0


# axl-api#141 regression coverage ---------------------------------------------
# Production bug: every hourly Polar sync landed status="partial" with
# "workouts: 1 validation error for ExerciseJSON" because a single real
# exercise (manually / phone-logged, missing `device`) failed validation and
# raised, downgrading the whole sync to "partial" with zero workouts saved.


def _build_polar_workouts() -> PolarWorkouts:
    from app.models import EventRecord, User
    from app.repositories.event_record_repository import EventRecordRepository
    from app.repositories.user_connection_repository import UserConnectionRepository
    from app.repositories.user_repository import UserRepository
    from app.services.providers.polar.oauth import PolarOAuth

    user_repo = UserRepository(User)
    connection_repo = UserConnectionRepository()
    workout_repo = EventRecordRepository(EventRecord)
    oauth = PolarOAuth(
        user_repo=user_repo,
        connection_repo=connection_repo,
        provider_name="polar",
        api_base_url="https://www.polaraccesslink.com",
    )
    return PolarWorkouts(
        workout_repo=workout_repo,
        connection_repo=connection_repo,
        provider_name="polar",
        api_base_url="https://www.polaraccesslink.com",
        oauth=oauth,
    )


class TestPolarExerciseJsonTolerance:
    """ExerciseJSON must tolerate the realistically-varying Polar fields (axl-api#141)."""

    def test_accepts_missing_device(self, sample_polar_exercise: dict) -> None:
        raw = {k: v for k, v in sample_polar_exercise.items() if k != "device"}
        exercise = PolarExerciseJSON(**raw)
        assert exercise.device is None

    def test_accepts_float_numeric_fields(self, sample_polar_exercise: dict) -> None:
        raw = {
            **sample_polar_exercise,
            "distance": 8500.5,
            "calories": 450.0,
            "start_time_utc_offset": 60.0,
        }
        exercise = PolarExerciseJSON(**raw)
        assert exercise.distance == 8500.5
        assert exercise.calories == 450.0
        assert exercise.start_time_utc_offset == 60.0

    def test_accepts_float_training_load_pro(self, sample_polar_exercise: dict) -> None:
        # Exact prod payload (axl-api#141): training-load-pro scores arrive as
        # floats; a required-int previously failed the whole exercise here.
        raw = {
            **sample_polar_exercise,
            "training_load_pro": {
                "date": "2024-01-15",
                "cardio-load": 68.1259,
                "muscle-load": 12.5,
                "perceived-load": 30.0,
            },
        }
        exercise = PolarExerciseJSON(**raw)
        assert exercise.training_load_pro is not None
        assert exercise.training_load_pro.cardio_load == 68.1259
        assert exercise.training_load_pro.muscle_load == 12.5

    def test_accepts_float_percentages_and_running_index(self, sample_polar_exercise: dict) -> None:
        raw = {
            **sample_polar_exercise,
            "fat_percentage": 42.5,
            "carbohydrate_percentage": 57.5,
            "running-index": 55.0,
        }
        exercise = PolarExerciseJSON(**raw)
        assert exercise.fat_percentage == 42.5
        assert exercise.running_index == 55.0


class TestPolarWorkoutsParseExercises:
    """_parse_exercises must skip (not raise on) malformed exercises (axl-api#141)."""

    def test_skips_malformed_and_keeps_good(self, sample_polar_exercise: dict) -> None:
        # One malformed exercise (missing required `sport`) must be skipped, not
        # raise and fail the whole batch -- the valid exercise still parses.
        bad = {k: v for k, v in sample_polar_exercise.items() if k != "sport"}
        bad["id"] = "bad-exercise"
        good = {**sample_polar_exercise, "id": "good-exercise"}
        workouts = _build_polar_workouts()

        parsed = workouts._parse_exercises([bad, good], uuid4())

        assert len(parsed) == 1
        assert parsed[0].id == "good-exercise"

    def test_keeps_device_less_exercise(self, sample_polar_exercise: dict) -> None:
        raw = {k: v for k, v in sample_polar_exercise.items() if k != "device"}
        workouts = _build_polar_workouts()

        parsed = workouts._parse_exercises([raw], uuid4())

        assert len(parsed) == 1
        assert parsed[0].device is None


class TestGetUnifiedWorkoutType:
    @pytest.mark.parametrize(
        ("sport", "detailed", "expected"),
        [
            ("CYCLING", "INDOOR_CYCLING", WorkoutType.INDOOR_CYCLING),
            ("OTHER", "JUMP_ROPE", WorkoutType.CARDIO_TRAINING),
            ("OTHER", "KICKBOXING_MARTIAL_ARTS", WorkoutType.BOXING),
        ],
    )
    def test_mappings(self, sport: str, detailed: str, expected: WorkoutType) -> None:
        assert get_unified_workout_type(sport, detailed) == expected


class TestPolarFitIngestion:
    """Polar's exercise JSON carries four metrics; everything else lives in the FIT file."""

    @pytest.fixture
    def workouts(self, db: Session) -> PolarWorkouts:
        from app.models import EventRecord, User
        from app.repositories.event_record_repository import EventRecordRepository
        from app.repositories.user_connection_repository import UserConnectionRepository
        from app.repositories.user_repository import UserRepository
        from app.services.providers.polar.oauth import PolarOAuth

        connection_repo = UserConnectionRepository()
        return PolarWorkouts(
            workout_repo=EventRecordRepository(EventRecord),
            connection_repo=connection_repo,
            provider_name="polar",
            api_base_url="https://www.polaraccesslink.com",
            oauth=PolarOAuth(
                user_repo=UserRepository(User),
                connection_repo=connection_repo,
                provider_name="polar",
                api_base_url="https://www.polaraccesslink.com",
            ),
        )

    def _save(
        self,
        workouts: PolarWorkouts,
        db: Session,
        user_id: UUID,
        raw: dict,
    ) -> None:
        exercise = PolarExerciseJSON(**raw)
        workouts._save_bundles(db, user_id, workouts._build_bundles([exercise], user_id))

    @patch("app.services.providers.polar.workouts.download_binary_content")
    def test_session_rollup_fills_fields_the_json_lacks(
        self,
        mock_download: MagicMock,
        workouts: PolarWorkouts,
        db: Session,
        sample_polar_exercise: dict,
    ) -> None:
        # Arrange
        from tests.fixtures.fit_builder import make_running_fit

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")
        mock_download.return_value = make_running_fit()

        # Act
        self._save(workouts, db, user.id, sample_polar_exercise)

        # Assert
        record = workouts.workout_repo.get_by_external_id(db, user.id, "ABC123", provider="polar")
        detail = record.workout_detail
        assert detail.average_speed == Decimal("3.2")
        assert detail.max_speed == Decimal("4.1")
        assert detail.average_cadence == Decimal("86")
        assert detail.average_watts == Decimal("245")
        assert detail.total_elevation_gain == Decimal("125")
        assert detail.moving_time_seconds == 20

    @patch("app.services.providers.polar.workouts.download_binary_content")
    def test_json_metrics_win_over_the_fit_rollup(
        self,
        mock_download: MagicMock,
        workouts: PolarWorkouts,
        db: Session,
        sample_polar_exercise: dict,
    ) -> None:
        """Polar's own rollup is authoritative where the two overlap."""
        # Arrange
        from tests.fixtures.fit_builder import make_running_fit

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")
        mock_download.return_value = make_running_fit()

        # Act
        self._save(workouts, db, user.id, sample_polar_exercise)

        # Assert — JSON says 10000 m / 650 kcal / 175 max HR, the synthetic FIT says otherwise
        detail = workouts.workout_repo.get_by_external_id(db, user.id, "ABC123", provider="polar").workout_detail
        assert detail.distance == Decimal("10000")
        assert detail.energy_burned == Decimal("650")
        assert detail.heart_rate_max == 175

    @patch("app.services.providers.polar.workouts.download_binary_content")
    def test_laps_are_stored_as_segments(
        self,
        mock_download: MagicMock,
        workouts: PolarWorkouts,
        db: Session,
        sample_polar_exercise: dict,
    ) -> None:
        # Arrange
        from tests.fixtures.fit_builder import make_running_fit

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")
        mock_download.return_value = make_running_fit()

        # Act
        self._save(workouts, db, user.id, sample_polar_exercise)

        # Assert
        detail = workouts.workout_repo.get_by_external_id(db, user.id, "ABC123", provider="polar").workout_detail
        assert len(detail.segments) == 2
        assert all(seg["kind"] == "lap" for seg in detail.segments)

    @patch("app.services.providers.polar.workouts.download_binary_content")
    def test_samples_are_persisted(
        self,
        mock_download: MagicMock,
        workouts: PolarWorkouts,
        db: Session,
        sample_polar_exercise: dict,
    ) -> None:
        # Arrange
        from app.models import DataPointSeries, DataSource
        from tests.fixtures.fit_builder import make_running_fit

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")
        mock_download.return_value = make_running_fit()

        # Act
        with patch("app.services.providers.polar.workouts.settings.ingest_workout_samples", True):
            self._save(workouts, db, user.id, sample_polar_exercise)

        # Assert
        db.flush()
        stored = (
            db.query(DataPointSeries)
            .join(DataSource, DataPointSeries.data_source_id == DataSource.id)
            .filter(DataSource.user_id == user.id)
            .count()
        )
        assert stored == 240, "every FIT sample should reach data_point_series"

    @patch("app.services.providers.polar.workouts.download_binary_content")
    def test_fit_is_not_refetched_on_a_re_cover(
        self,
        mock_download: MagicMock,
        workouts: PolarWorkouts,
        db: Session,
        sample_polar_exercise: dict,
    ) -> None:
        """Sync windows re-cover the same exercise hourly; the FIT is immutable."""
        # Arrange
        from tests.fixtures.fit_builder import make_running_fit

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")
        mock_download.return_value = make_running_fit()

        # Act
        self._save(workouts, db, user.id, sample_polar_exercise)
        db.flush()
        self._save(workouts, db, user.id, sample_polar_exercise)

        # Assert
        assert mock_download.call_count == 1

    @patch("app.services.providers.polar.workouts.log_and_capture_error")
    @patch("app.services.providers.polar.workouts.download_binary_content")
    def test_missing_fit_is_quiet_and_still_saves_the_workout(
        self,
        mock_download: MagicMock,
        mock_capture: MagicMock,
        workouts: PolarWorkouts,
        db: Session,
        sample_polar_exercise: dict,
    ) -> None:
        """Phone-logged exercises have no recorded file; that is not a failure.

        The raise is httpx.HTTPStatusError, because download_binary_content surfaces the
        status through response.raise_for_status() rather than the fastapi HTTPException
        the JSON paths raise. Catching only the latter left the quiet branch dead and sent
        a Sentry event per sync window, forever, for an exercise that will never have a file.
        """
        # Arrange
        import httpx

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")
        request = httpx.Request("GET", "https://www.polaraccesslink.com/v3/exercises/ABC123/fit")
        mock_download.side_effect = httpx.HTTPStatusError(
            "404", request=request, response=httpx.Response(404, request=request)
        )

        # Act
        self._save(workouts, db, user.id, sample_polar_exercise)

        # Assert
        detail = workouts.workout_repo.get_by_external_id(db, user.id, "ABC123", provider="polar").workout_detail
        assert detail.distance == Decimal("10000")
        assert detail.average_speed is None
        mock_capture.assert_not_called()

    @patch("app.services.providers.polar.workouts.log_and_capture_error")
    @patch("app.services.providers.polar.workouts.download_binary_content")
    def test_a_real_download_failure_is_still_reported(
        self,
        mock_download: MagicMock,
        mock_capture: MagicMock,
        workouts: PolarWorkouts,
        db: Session,
        sample_polar_exercise: dict,
    ) -> None:
        """Only "no such file" is quiet -- a 500 is a genuine problem."""
        # Arrange
        import httpx

        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")
        request = httpx.Request("GET", "https://www.polaraccesslink.com/v3/exercises/ABC123/fit")
        mock_download.side_effect = httpx.HTTPStatusError(
            "500", request=request, response=httpx.Response(500, request=request)
        )

        # Act
        self._save(workouts, db, user.id, sample_polar_exercise)

        # Assert
        assert workouts.workout_repo.get_by_external_id(db, user.id, "ABC123", provider="polar") is not None
        mock_capture.assert_called_once()

    @patch("app.services.providers.polar.workouts.download_binary_content")
    def test_unparseable_fit_still_saves_the_workout(
        self,
        mock_download: MagicMock,
        workouts: PolarWorkouts,
        db: Session,
        sample_polar_exercise: dict,
    ) -> None:
        # Arrange
        user = UserFactory()
        UserConnectionFactory(user=user, provider="polar")
        mock_download.return_value = b"not a fit file"

        # Act
        self._save(workouts, db, user.id, sample_polar_exercise)

        # Assert
        record = workouts.workout_repo.get_by_external_id(db, user.id, "ABC123", provider="polar")
        assert record is not None
        assert record.workout_detail.distance == Decimal("10000")
