"""Tests for the unauthenticated /health endpoint (build version probe)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import settings


class TestHealthEndpoint:
    def test_returns_ok_and_version(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body == {"status": "ok", "version": settings.app_version}

    def test_version_matches_openapi_info(self, client: TestClient) -> None:
        # The /health version and FastAPI's info.version share one source, so
        # /openapi.json no longer reports a stale hardcoded value.
        health_version = client.get("/health").json()["version"]
        openapi_version = client.get("/openapi.json").json()["info"]["version"]

        assert health_version == openapi_version == settings.app_version
