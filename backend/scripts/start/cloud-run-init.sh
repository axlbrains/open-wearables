#!/bin/bash
set -e -x

echo 'Applying migrations...'
uv run alembic upgrade head

echo 'Initializing provider settings...'
uv run python scripts/init_provider_settings.py

echo 'Initializing priorities...'
uv run python scripts/init_device_priorities.py

echo 'Seeding admin account...'
uv run python scripts/init/seed_admin.py

echo 'Initializing series type definitions...'
uv run python scripts/init/seed_series_types.py
