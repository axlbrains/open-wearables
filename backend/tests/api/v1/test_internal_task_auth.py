"""OIDC check on the worker's internal task API (fork: the worker runs off Cloud Run)."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.routes.v1 import internal_tasks
from app.api.routes.v1.internal_tasks import verify_task_caller
from app.config import settings
from app.integrations import google_auth

AUDIENCE = "https://ow-api.example.test"
TASKS_SA = "tasks@project.iam.gserviceaccount.com"


@pytest.fixture
def oidc_on(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setattr(settings, "internal_task_oidc_audience", AUDIENCE)
    monkeypatch.setattr(settings, "internal_task_allowed_service_accounts", [TASKS_SA])
    verify = MagicMock(return_value={"email": TASKS_SA, "email_verified": True})
    monkeypatch.setattr(internal_tasks.id_token, "verify_oauth2_token", verify)
    return verify


def test_no_audience_means_no_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "internal_task_oidc_audience", None)
    verify_task_caller(None)


def test_allowed_service_account_passes(oidc_on: MagicMock) -> None:
    verify_task_caller("Bearer good-token")
    oidc_on.assert_called_once()
    assert oidc_on.call_args.args[0] == "good-token"
    assert oidc_on.call_args.args[2] == AUDIENCE


@pytest.mark.parametrize("header", [None, "", "Basic abc", "good-token"])
def test_missing_bearer_is_401(oidc_on: MagicMock, header: str | None) -> None:
    with pytest.raises(HTTPException) as exc:
        verify_task_caller(header)
    assert exc.value.status_code == 401
    oidc_on.assert_not_called()


def test_bad_signature_or_audience_is_401(oidc_on: MagicMock) -> None:
    oidc_on.side_effect = ValueError("Token has wrong audience")
    with pytest.raises(HTTPException) as exc:
        verify_task_caller("Bearer forged")
    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "someone-else@project.iam.gserviceaccount.com", "email_verified": True},
        {"email": TASKS_SA, "email_verified": False},
        {"sub": "123"},
    ],
)
def test_other_caller_is_403(oidc_on: MagicMock, claims: dict) -> None:
    oidc_on.return_value = claims
    with pytest.raises(HTTPException) as exc:
        verify_task_caller("Bearer valid-but-not-ours")
    assert exc.value.status_code == 403


def test_allowed_accounts_parse_from_comma_list() -> None:
    parsed = type(settings).model_validate(
        {"internal_task_allowed_service_accounts": f" {TASKS_SA}, other@p.iam.gserviceaccount.com ,"}
    )
    assert parsed.internal_task_allowed_service_accounts == [TASKS_SA, "other@p.iam.gserviceaccount.com"]


def test_access_token_from_key_file_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_application_credentials", "/run/secrets/gcp.json")
    monkeypatch.setattr(google_auth, "_credentials", None)
    creds = MagicMock(valid=False, token="ya29.token")

    def refresh(_request: object) -> None:
        creds.valid = True

    creds.refresh.side_effect = refresh
    load = MagicMock(return_value=(creds, "project"))
    monkeypatch.setattr(google_auth.google.auth, "load_credentials_from_file", load)
    metadata = MagicMock()
    monkeypatch.setattr(google_auth.httpx, "get", metadata)

    assert google_auth.get_google_access_token() == "ya29.token"
    assert google_auth.get_google_access_token() == "ya29.token"

    load.assert_called_once_with("/run/secrets/gcp.json", scopes=[google_auth._CLOUD_PLATFORM_SCOPE])
    creds.refresh.assert_called_once()
    metadata.assert_not_called()
