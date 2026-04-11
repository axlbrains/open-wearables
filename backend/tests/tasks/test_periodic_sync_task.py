"""
Tests for sync_all_users periodic Celery task.

Tests the periodic task that syncs data for all users with active connections.
"""

from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from app.integrations.celery.tasks.periodic_sync_task import sync_all_users
from app.integrations.task_dispatcher import RegisteredTask
from app.schemas.auth import ConnectionStatus
from tests.factories import UserConnectionFactory, UserFactory


def _dispatch_user_ids(mock_dispatch: MagicMock) -> list[str]:
    """Extract user_id kwargs from dispatch_task calls for assertions."""
    return [call.kwargs["kwargs"]["user_id"] for call in mock_dispatch.call_args_list]


class TestSyncAllUsersTask:
    """Test suite for sync_all_users periodic task."""

    @patch("app.integrations.celery.tasks.periodic_sync_task.SessionLocal")
    @patch("app.integrations.celery.tasks.periodic_sync_task.dispatch_task")
    def test_sync_all_users_with_active_connections(
        self,
        mock_dispatch: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test syncing all users with active connections."""
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()

        UserConnectionFactory(user=user1, provider="garmin", status=ConnectionStatus.ACTIVE)
        UserConnectionFactory(user=user2, provider="polar", status=ConnectionStatus.ACTIVE)
        UserConnectionFactory(user=user3, provider="suunto", status=ConnectionStatus.ACTIVE)

        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)

        result = sync_all_users()

        assert result["users_for_sync"] == 3
        assert mock_dispatch.call_count == 3

        for call in mock_dispatch.call_args_list:
            assert call.args[0] == RegisteredTask.SYNC_VENDOR_DATA

        dispatched_user_ids = _dispatch_user_ids(mock_dispatch)
        assert str(user1.id) in dispatched_user_ids
        assert str(user2.id) in dispatched_user_ids
        assert str(user3.id) in dispatched_user_ids

    @patch("app.integrations.celery.tasks.periodic_sync_task.SessionLocal")
    @patch("app.integrations.celery.tasks.periodic_sync_task.dispatch_task")
    def test_sync_all_users_with_date_range(
        self,
        mock_dispatch: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test syncing all users with specific date range."""
        user = UserFactory()
        UserConnectionFactory(user=user, provider="garmin", status=ConnectionStatus.ACTIVE)

        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)

        start_date = "2025-01-01T00:00:00Z"
        end_date = "2025-12-31T23:59:59Z"

        result = sync_all_users(start_date=start_date, end_date=end_date)

        assert result["users_for_sync"] == 1
        mock_dispatch.assert_called_once_with(
            RegisteredTask.SYNC_VENDOR_DATA,
            kwargs={
                "user_id": str(user.id),
                "start_date": start_date,
                "end_date": end_date,
            },
        )

    @patch("app.integrations.celery.tasks.periodic_sync_task.SessionLocal")
    @patch("app.integrations.celery.tasks.periodic_sync_task.dispatch_task")
    def test_sync_all_users_skips_disconnected_users(
        self,
        mock_dispatch: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test that users without active connections are not synced."""
        user1 = UserFactory()
        user2 = UserFactory()

        UserConnectionFactory(user=user1, provider="garmin", status=ConnectionStatus.ACTIVE)
        UserConnectionFactory(user=user2, provider="polar", status=ConnectionStatus.REVOKED)

        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)

        result = sync_all_users()

        assert result["users_for_sync"] == 1
        mock_dispatch.assert_called_once()

        dispatched_user_ids = _dispatch_user_ids(mock_dispatch)
        assert dispatched_user_ids == [str(user1.id)]

    @patch("app.integrations.celery.tasks.periodic_sync_task.SessionLocal")
    @patch("app.integrations.celery.tasks.periodic_sync_task.dispatch_task")
    def test_sync_all_users_no_users(
        self,
        mock_dispatch: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test syncing when no users have active connections."""
        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)

        result = sync_all_users()

        assert result["users_for_sync"] == 0
        mock_dispatch.assert_not_called()

    @patch("app.integrations.celery.tasks.periodic_sync_task.SessionLocal")
    @patch("app.integrations.celery.tasks.periodic_sync_task.dispatch_task")
    def test_sync_all_users_multiple_connections_per_user(
        self,
        mock_dispatch: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test that users with multiple connections are only queued once."""
        user = UserFactory()

        UserConnectionFactory(user=user, provider="garmin", status=ConnectionStatus.ACTIVE)
        UserConnectionFactory(user=user, provider="polar", status=ConnectionStatus.ACTIVE)
        UserConnectionFactory(user=user, provider="suunto", status=ConnectionStatus.ACTIVE)

        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)

        result = sync_all_users()

        assert result["users_for_sync"] == 1
        mock_dispatch.assert_called_once_with(
            RegisteredTask.SYNC_VENDOR_DATA,
            kwargs={"user_id": str(user.id), "start_date": None, "end_date": None},
        )

    @patch("app.integrations.celery.tasks.periodic_sync_task.SessionLocal")
    @patch("app.integrations.celery.tasks.periodic_sync_task.dispatch_task")
    def test_sync_all_users_mixed_connection_statuses(
        self,
        mock_dispatch: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test syncing users with mixed connection statuses."""
        user1 = UserFactory()
        user2 = UserFactory()
        user3 = UserFactory()

        UserConnectionFactory(user=user1, provider="garmin", status=ConnectionStatus.ACTIVE)
        UserConnectionFactory(user=user2, provider="polar", status=ConnectionStatus.ACTIVE)
        UserConnectionFactory(user=user2, provider="suunto", status=ConnectionStatus.REVOKED)
        UserConnectionFactory(user=user3, provider="garmin", status=ConnectionStatus.REVOKED)

        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)

        result = sync_all_users()

        assert result["users_for_sync"] == 2  # Only user1 and user2
        assert mock_dispatch.call_count == 2

        dispatched_user_ids = _dispatch_user_ids(mock_dispatch)
        assert str(user1.id) in dispatched_user_ids
        assert str(user2.id) in dispatched_user_ids
        assert str(user3.id) not in dispatched_user_ids

    @patch("app.integrations.celery.tasks.periodic_sync_task.SessionLocal")
    @patch("app.integrations.celery.tasks.periodic_sync_task.dispatch_task")
    def test_sync_all_users_queues_async_tasks(
        self,
        mock_dispatch: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test that sync tasks are dispatched asynchronously."""
        user = UserFactory()
        UserConnectionFactory(user=user, provider="garmin", status=ConnectionStatus.ACTIVE)

        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)

        sync_all_users()

        mock_dispatch.assert_called_once()
        dispatched_task = mock_dispatch.call_args.args[0]
        assert dispatched_task == RegisteredTask.SYNC_VENDOR_DATA

    @patch("app.integrations.celery.tasks.periodic_sync_task.SessionLocal")
    @patch("app.integrations.celery.tasks.periodic_sync_task.dispatch_task")
    def test_sync_all_users_large_batch(
        self,
        mock_dispatch: MagicMock,
        mock_session_local: MagicMock,
        db: Session,
        mock_celery_app: MagicMock,
    ) -> None:
        """Test syncing a large number of users."""
        users = []
        for _ in range(10):
            user = UserFactory()
            users.append(user)
            UserConnectionFactory(user=user, provider="garmin", status=ConnectionStatus.ACTIVE)

        mock_session_local.return_value.__enter__ = MagicMock(return_value=db)
        mock_session_local.return_value.__exit__ = MagicMock(return_value=None)

        result = sync_all_users()

        assert result["users_for_sync"] == 10
        assert mock_dispatch.call_count == 10

        dispatched_user_ids = _dispatch_user_ids(mock_dispatch)
        for user in users:
            assert str(user.id) in dispatched_user_ids
