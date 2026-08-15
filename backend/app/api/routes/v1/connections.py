import contextlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.config import settings
from app.database import DbSession
from app.integrations.task_dispatcher import RegisteredTask, dispatch_task
from app.models import ProviderSetting
from app.repositories.provider_settings_repository import ProviderSettingsRepository
from app.schemas.auth import ConnectionStatus, LiveSyncMode
from app.schemas.enums import ProviderName
from app.schemas.model_crud.user_management import ApiKeyConnectRequest, UserConnectionWithCapabilities
from app.services import ApiKeyDep, user_connection_service
from app.services.providers.base_strategy import InvalidApiKeyError
from app.services.providers.factory import ProviderFactory

router = APIRouter()
factory = ProviderFactory()
provider_settings_repo = ProviderSettingsRepository()


def _with_capabilities(
    conn: object,
    settings_map: dict[str, ProviderSetting],
    linked_user_ids: list | None = None,
) -> UserConnectionWithCapabilities:
    enriched = UserConnectionWithCapabilities.model_validate(conn)
    with contextlib.suppress(ValueError):
        strategy = factory.get_provider(enriched.provider)
        caps = strategy.capabilities
        enriched.icon_url = strategy.icon_url
        enriched.max_historical_days = caps.max_historical_days
        enriched.rest_pull = caps.rest_pull
        enriched.webhook_stream = caps.webhook_stream
        enriched.webhook_ping = caps.webhook_ping
        enriched.webhook_callback = caps.webhook_callback
        setting = settings_map.get(enriched.provider)
        mode = (
            setting.live_sync_mode
            if (setting and setting.live_sync_mode is not None)
            else strategy.default_live_sync_mode
        )
        # ORM yields a plain str and attribute assignment skips validation; coerce to the enum
        enriched.live_sync_mode = LiveSyncMode(mode) if mode is not None else None
    if linked_user_ids:
        enriched.linked_user_ids = linked_user_ids
    return enriched


@router.get("/users/{user_id}/connections", response_model=list[UserConnectionWithCapabilities])
def get_connections_endpoint(
    user_id: UUID,
    db: DbSession,
    _api_key: ApiKeyDep,
):
    """Get all connections for a user, enriched with provider capability metadata."""
    settings_map = provider_settings_repo.get_all(db)
    connections = user_connection_service.get_connections_by_user(db, user_id)
    provider_pairs = [
        (c.provider, c.provider_user_id)
        for c in connections
        if c.provider_user_id and c.status == ConnectionStatus.ACTIVE
    ]
    linked_map = user_connection_service.get_linked_user_ids(db, user_id, provider_pairs)
    return [
        _with_capabilities(
            conn,
            settings_map,
            linked_map.get((conn.provider, conn.provider_user_id)) if conn.provider_user_id else None,
        )
        for conn in connections
    ]


@router.post(
    "/users/{user_id}/connections/{provider}",
    response_model=UserConnectionWithCapabilities,
    status_code=status.HTTP_201_CREATED,
)
def connect_provider_with_api_key_endpoint(
    user_id: UUID,
    provider: ProviderName,
    body: ApiKeyConnectRequest,
    db: DbSession,
    _api_key: ApiKeyDep,
):
    """Connect a user to an API-key provider (no OAuth) by validating and storing their key.

    Only providers with ``capabilities.api_key_connect`` (e.g. Hevy) accept this;
    OAuth providers must go through /oauth/{provider}/authorize.
    """
    strategy = factory.get_provider(provider.value)
    if not strategy.capabilities.api_key_connect:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider {provider.value} does not support API-key connect; use the OAuth flow",
        )
    try:
        # Strategies with api_key_connect=True implement connect_with_api_key.
        connection = strategy.connect_with_api_key(db, user_id, body.api_key)  # type: ignore[attr-defined]
    except InvalidApiKeyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    # Mirror the OAuth callback post-connect behavior: cursor to now, then a
    # 90-day historical backfill (flag-gated) off the request thread.
    user_connection_service.stamp_last_synced_at(db, user_id, provider.value)
    if settings.historical_sync_on_connect and strategy.capabilities.rest_pull:
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=90)).isoformat()
        end_date = now.isoformat()
        dispatch_task(
            RegisteredTask.SYNC_VENDOR_DATA,
            kwargs={
                "user_id": str(user_id),
                "start_date": start_date,
                "end_date": end_date,
                "providers": [provider.value],
                "is_historical": True,
            },
            dedup_key=f"sync_vendor:{user_id}:{provider.value}:{start_date}:{end_date}:h",
        )

    settings_map = provider_settings_repo.get_all(db)
    return _with_capabilities(connection, settings_map)


@router.delete("/users/{user_id}/connections/{provider}")
def disconnect_provider_endpoint(
    user_id: UUID,
    provider: ProviderName,
    db: DbSession,
    _api_key: ApiKeyDep,
) -> Response:
    """Disconnect a user from a provider, revoking the connection and clearing tokens."""
    strategy = ProviderFactory().get_provider(provider.value)
    user_connection_service.disconnect(db, user_id, provider.value, oauth=strategy.oauth)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/users/{user_id}/connections/{provider}/data")
def delete_provider_data_endpoint(
    user_id: UUID,
    provider: ProviderName,
    db: DbSession,
    _api_key: ApiKeyDep,
) -> Response:
    """Delete all of a user's data for a provider and revoke the connection."""
    strategy = ProviderFactory().get_provider(provider.value)
    user_connection_service.purge_provider_data(db, user_id, provider.value, oauth=strategy.oauth)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
