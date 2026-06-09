"""Tests for the global unhandled-exception handler (axlbrains/open-wearables#22).

Verifies that an uncaught error is logged with a full traceback before the
request returns 500 — so production 5xx are root-causable instead of silent.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.main import api

# Register a route that always raises an uncaught error. A unique path keeps it
# inert for the rest of the suite.
_BOOM_PATH = "/_test_unhandled_exception"


@api.get(_BOOM_PATH)
def _boom() -> None:
    raise RuntimeError("boom for test")


class TestUnhandledExceptionHandler:
    def test_returns_500_json_and_logs_traceback(self, caplog: pytest.LogCaptureFixture) -> None:
        # raise_server_exceptions=False so the handler runs instead of the error
        # propagating out of the test client (mirrors real server behaviour).
        client = TestClient(api, raise_server_exceptions=False)

        with caplog.at_level(logging.ERROR, logger="app.main"):
            response = client.get(_BOOM_PATH)

        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR and r.name == "app.main"]
        assert len(errors) == 1
        record = errors[0]
        assert _BOOM_PATH in record.getMessage()
        # exc_info present => a full traceback was captured for root-causing.
        assert record.exc_info is not None
        assert record.exc_info[0] is RuntimeError
