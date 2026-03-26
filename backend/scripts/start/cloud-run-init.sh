#!/bin/bash
set -e -x

echo 'Applying migrations...'
/root_project/.venv/bin/alembic upgrade head

echo 'Initializing provider settings...'
/root_project/.venv/bin/python scripts/init_provider_settings.py

echo 'Initializing priorities...'
/root_project/.venv/bin/python scripts/init_device_priorities.py

echo 'Seeding admin account...'
/root_project/.venv/bin/python scripts/init/seed_admin.py

echo 'Initializing series type definitions...'
/root_project/.venv/bin/python scripts/init/seed_series_types.py
