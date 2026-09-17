"""Tests for the legacy ``google`` provider split, focused on the seed-order collision.

``provider_settings.provider`` is the primary key, so on a deployment whose seeding ran
before this migration the target row already exists and a bare rename aborts the whole
transaction — which means nothing moves, including the user_connection rows that make
``factory.get_provider("google")`` raise on every sync.
See scripts/data_migrations/split_google_provider.py.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

from sqlalchemy import text
from sqlalchemy.orm import Session

LEGACY = "google"
API = "google_health"
SDK = "health_connect"

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "data_migrations" / "split_google_provider.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("split_google_provider", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


split = _load_module().split_google_provider


def _settings(db: Session, provider: str, *, live_sync_mode: str | None = None) -> None:
    db.execute(
        text(
            "INSERT INTO provider_settings (provider, is_enabled, live_sync_mode)"
            " VALUES (:p, true, :m)"
            " ON CONFLICT (provider) DO UPDATE SET live_sync_mode = EXCLUDED.live_sync_mode"
        ),
        {"p": provider, "m": live_sync_mode},
    )


def _providers(db: Session) -> set[str]:
    return {
        row[0]
        for row in db.execute(
            text("SELECT provider FROM provider_settings WHERE provider IN (:l, :a, :s)"),
            {"l": LEGACY, "a": API, "s": SDK},
        )
    }


class TestProviderSettingsCollision:
    def test_rename_when_no_target_row_exists(self, db: Session) -> None:
        # Arrange
        db.execute(text("DELETE FROM provider_settings WHERE provider IN (:a, :s)"), {"a": API, "s": SDK})
        _settings(db, LEGACY, live_sync_mode="pull")

        # Act
        result = split(db, dry_run=False)

        # Assert
        assert result["provider_settings"] == 1
        assert _providers(db) == {API}

    def test_seeded_target_does_not_abort_the_migration(self, db: Session) -> None:
        """The collision case: seeding already created the target row."""
        # Arrange
        _settings(db, LEGACY, live_sync_mode="pull")
        _settings(db, API, live_sync_mode=None)

        # Act
        result = split(db, dry_run=False)

        # Assert
        assert result["provider_settings"] == 1
        assert _providers(db) >= {API}
        assert LEGACY not in _providers(db)

    def test_legacy_settings_survive_the_fold(self, db: Session) -> None:
        """The seeded row is a default; the legacy row is what the deployment was running."""
        # Arrange
        _settings(db, LEGACY, live_sync_mode="pull")
        _settings(db, API, live_sync_mode=None)

        # Act
        split(db, dry_run=False)

        # Assert
        mode = db.execute(
            text("SELECT live_sync_mode FROM provider_settings WHERE provider = :p"), {"p": API}
        ).scalar()
        assert mode == "pull"

    def test_is_idempotent(self, db: Session) -> None:
        # Arrange
        _settings(db, LEGACY, live_sync_mode="pull")
        _settings(db, API, live_sync_mode=None)

        # Act
        split(db, dry_run=False)
        second = split(db, dry_run=False)

        # Assert
        assert second["provider_settings"] == 0
        assert LEGACY not in _providers(db)
