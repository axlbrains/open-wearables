"""Tests for the task dispatcher abstraction."""

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.task_dispatcher import RegisteredTask, dispatch_task


class TestRegisteredTask:
    """The registry enum is the single source of truth for background tasks."""

    def test_values_are_fully_qualified_celery_task_names(self) -> None:
        """Enum values must match the task name used by @shared_task.

        Celery resolves tasks by their fully qualified name (module + function),
        so each enum value has to be a valid import path ending in the function
        that carries the @shared_task decorator.
        """
        for task in RegisteredTask:
            assert task.value.startswith("app.integrations.celery.tasks."), (
                f"RegisteredTask.{task.name} must use the canonical Celery task name; "
                f"got {task.value!r}"
            )

    def test_values_are_unique(self) -> None:
        """Two different registered tasks must not share a name."""
        values = [task.value for task in RegisteredTask]
        assert len(values) == len(set(values))


class TestDispatchTask:
    """`dispatch_task` delegates to the configured task backend."""

    def test_delegates_to_celery_send_task(self) -> None:
        with patch("app.integrations.task_dispatcher.celery") as mock_celery_module:
            mock_celery = mock_celery_module.current_app
            mock_celery.send_task.return_value = MagicMock(id="task-123")

            result = dispatch_task(
                RegisteredTask.SYNC_VENDOR_DATA,
                kwargs={"user_id": "abc", "start_date": None, "end_date": None},
            )

            mock_celery.send_task.assert_called_once_with(
                RegisteredTask.SYNC_VENDOR_DATA.value,
                args=[],
                kwargs={"user_id": "abc", "start_date": None, "end_date": None},
                countdown=None,
            )
            assert result.id == "task-123"

    def test_propagates_args_and_countdown(self) -> None:
        with patch("app.integrations.task_dispatcher.celery") as mock_celery_module:
            mock_celery = mock_celery_module.current_app
            mock_celery.send_task.return_value = MagicMock()

            dispatch_task(
                RegisteredTask.TRIGGER_GARMIN_BACKFILL_FOR_TYPE,
                args=["user-uuid", "activities"],
                countdown=5,
            )

            _, kwargs = mock_celery.send_task.call_args
            assert kwargs["args"] == ["user-uuid", "activities"]
            assert kwargs["countdown"] == 5

    def test_defaults_args_and_kwargs_to_empty(self) -> None:
        with patch("app.integrations.task_dispatcher.celery") as mock_celery_module:
            mock_celery = mock_celery_module.current_app
            mock_celery.send_task.return_value = MagicMock()

            dispatch_task(RegisteredTask.FINALIZE_STALE_SLEEPS)

            _, kwargs = mock_celery.send_task.call_args
            assert kwargs["args"] == []
            assert kwargs["kwargs"] == {}

    def test_rejects_non_enum_input(self) -> None:
        """Passing a plain string would bypass the registry and defeat the point."""
        with pytest.raises(AttributeError):
            dispatch_task("app.integrations.celery.tasks.sync_vendor_data_task.sync_vendor_data")  # type: ignore[arg-type]
