import threading

import google.auth
import httpx
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

_GOOGLE_METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)
_GOOGLE_METADATA_HEADERS = {"Metadata-Flavor": "Google"}
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

_credentials: Credentials | None = None
_credentials_lock = threading.Lock()


def _token_from_key_file(key_file: str) -> str:
    """Access token from a service account key file, cached and refreshed before expiry.

    Off Google Cloud (e.g. a plain VPS) there is no metadata server, so the host is given
    a key file through GOOGLE_APPLICATION_CREDENTIALS instead.
    """
    global _credentials
    with _credentials_lock:
        if _credentials is None:
            _credentials, _ = google.auth.load_credentials_from_file(key_file, scopes=[_CLOUD_PLATFORM_SCOPE])
        if not _credentials.valid:
            _credentials.refresh(GoogleAuthRequest())
        token = _credentials.token
    if not token:
        raise ValueError("Google service account credentials did not yield an access token")
    return token


def get_google_access_token() -> str:
    from app.config import settings

    if settings.google_application_credentials:
        return _token_from_key_file(settings.google_application_credentials)

    response = httpx.get(_GOOGLE_METADATA_TOKEN_URL, headers=_GOOGLE_METADATA_HEADERS, timeout=5.0)
    response.raise_for_status()
    token_payload = response.json()
    access_token = token_payload.get("access_token")
    if not access_token:
        raise ValueError("Google metadata server did not return an access token")
    return access_token
