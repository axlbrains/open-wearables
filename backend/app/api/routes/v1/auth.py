from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm

from app.config import settings
from app.database import DbSession
from app.schemas.auth import TokenResponse
from app.schemas.enums.provider import ProviderName
from app.schemas.model_crud.user_management import DeveloperRead, DeveloperUpdate, PasswordChange
from app.services import DeveloperDep, developer_service, refresh_token_service
from app.services.application_service import application_service
from app.services.providers.factory import ProviderFactory
from app.utils.security import create_access_token, verify_password

router = APIRouter()


@router.post("/login")
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
) -> TokenResponse:
    """Authenticate developer and return access token with refresh token."""
    # Find developer by email
    developers = developer_service.crud.get_all(
        db,
        filters={"email": form_data.username},
        offset=0,
        limit=1,
        sort_by=None,
    )
    if not developers:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    developer = developers[0]
    if not verify_password(form_data.password, developer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=str(developer.id))
    refresh_token = refresh_token_service.create_developer_refresh_token(db, developer.id)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout")
def logout(_developer: DeveloperDep):
    """Logout developer (token invalidation should be handled client-side)."""
    return {"message": "Successfully logged out"}


@router.post("/change-password")
def change_password(
    payload: PasswordChange,
    db: DbSession,
    developer: DeveloperDep,
):
    """Change password for the current authenticated developer."""
    # Verify the current password
    if not verify_password(payload.current_password, developer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password",
        )

    # Update using existing developer_service logic
    developer_service.update_developer_info(
        db, developer.id, DeveloperUpdate(password=payload.new_password), raise_404=True
    )

    return {"message": "Password updated successfully"}


@router.get("/me", response_model=DeveloperRead)
def get_current_developer_info(db: DbSession, developer: DeveloperDep):
    """Get current authenticated developer."""
    return developer


@router.patch("/me", response_model=DeveloperRead)
def update_current_developer(
    payload: DeveloperUpdate,
    db: DbSession,
    developer: DeveloperDep,
):
    """Update current authenticated developer."""
    return developer_service.update_developer_info(db, developer.id, payload)


@router.get("/connect/{provider}")
async def connect_provider_via_app(
    provider: ProviderName,
    user_id: Annotated[UUID, Query(description="User ID to connect")],
    app_id: Annotated[str, Query(description="Application ID")],
    app_secret: Annotated[str, Query(description="Application Secret")],
    db: DbSession,
    redirect_uri: Annotated[str | None, Query(description="Optional redirect URI after authorization")] = None,
):
    """Connect a provider via application credentials (redirect to OAuth flow)."""
    application_service.validate_credentials(db, app_id, app_secret)

    try:
        strategy = ProviderFactory().get_provider(provider.value)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not strategy.oauth:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{provider.value}' does not support OAuth",
        )

    auth_url, _state = strategy.oauth.get_authorization_url(user_id, redirect_uri)
    return RedirectResponse(url=auth_url)
