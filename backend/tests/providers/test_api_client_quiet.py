"""A provider saying "no data for you" must not be logged as our failure.

Two shapes cost us ~130 error-level lines a day for a single Polar athlete:
an empty body (Polar's "nothing new here") parsed as JSON, and a 404 on an
endpoint the athlete's device or consent does not cover. Both were already
handled as "no data" by the caller — only the api_client's own logging, which
runs *before* the caller sees the response, kept reporting them.
See the "someone else's no-data is not our error" section in CLAUDE.md.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from app.services.providers.api_client import make_authenticated_request

_ENDPOINT = "/v3/users/nightly-recharge"


def _response(status_code: int, content: bytes) -> httpx.Response:
    request = httpx.Request("GET", f"https://www.polaraccesslink.com{_ENDPOINT}")
    return httpx.Response(status_code, content=content, request=request)


def _call(response: httpx.Response, **kwargs: object) -> object:
    """Drive make_authenticated_request against a canned response."""
    client = MagicMock()
    client.__enter__.return_value.request.return_value = response
    with (
        patch("app.services.providers.api_client._get_valid_token", return_value="tok"),
        patch("app.services.providers.api_client.httpx.Client", return_value=client),
        patch("app.services.providers.api_client.log_structured") as mock_log,
    ):
        try:
            result = make_authenticated_request(
                db=MagicMock(),
                user_id=uuid4(),
                connection_repo=MagicMock(),
                oauth=MagicMock(),
                api_base_url="https://www.polaraccesslink.com",
                provider_name="polar",
                endpoint=_ENDPOINT,
                **kwargs,  # ty: ignore[invalid-argument-type]
            )
        except HTTPException as exc:
            result = exc
    return result, mock_log


def _error_calls(mock_log: MagicMock) -> list:
    return [c for c in mock_log.call_args_list if len(c.args) > 1 and c.args[1] == "error"]


class TestEmptyBodyIsNoContent:
    """Polar answers several endpoints with 204 / an empty body when there is nothing."""

    @pytest.mark.parametrize(
        ("status_code", "content"),
        [(204, b""), (200, b""), (200, b"   \n")],
        ids=["204", "200-empty", "200-whitespace"],
    )
    def test_returns_none_instead_of_raising(self, status_code: int, content: bytes) -> None:
        # Act
        result, mock_log = _call(_response(status_code, content))

        # Assert
        assert result is None, "an empty body is no content, not a parse failure"
        assert _error_calls(mock_log) == []

    def test_a_real_body_still_parses(self) -> None:
        # Act
        result, _ = _call(_response(200, b'{"ok": true}'))

        # Assert
        assert result == {"ok": True}


class TestQuietStatuses:
    """The caller knows which statuses it expects; api_client cannot."""

    def test_an_expected_status_is_not_logged_as_an_error(self) -> None:
        # Act
        result, mock_log = _call(_response(404, b"not found"), quiet_statuses=(401, 404))

        # Assert — still raises, so the caller's flow is unchanged
        assert isinstance(result, HTTPException)
        assert result.status_code == 404
        assert _error_calls(mock_log) == []

    def test_an_unexpected_status_stays_loud(self) -> None:
        # Act
        result, mock_log = _call(_response(500, b"boom"), quiet_statuses=(401, 404))

        # Assert
        assert isinstance(result, HTTPException)
        assert _error_calls(mock_log), "a 500 is not the provider saying 'no data'"

    def test_quiet_is_opt_in(self) -> None:
        """Without the caller opting in, a 404 is reported as before."""
        # Act
        _, mock_log = _call(_response(404, b"not found"))

        # Assert
        assert _error_calls(mock_log)

    def test_the_error_log_names_the_endpoint(self) -> None:
        """The old payload carried no endpoint, so the noise could not be attributed."""
        # Act
        _, mock_log = _call(_response(500, b"boom"))

        # Assert
        assert _error_calls(mock_log)[0].kwargs.get("endpoint") == _ENDPOINT
