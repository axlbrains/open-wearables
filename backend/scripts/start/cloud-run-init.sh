#!/bin/bash
set -e -x

echo 'Applying migrations...'
/opt/venv/bin/alembic upgrade head

# Splits the legacy `google` provider into health_connect (SDK) and google_health
# (cloud OAuth). Must stay ahead of init_provider_settings.py, which seeds a google_health
# row that the rename would collide with. Idempotent, no-op once split.
# Upstream runs this from scripts/start/app.sh, which prod never executes.
echo 'Running google provider split...'
/opt/venv/bin/python scripts/data_migrations/split_google_provider.py \
    || echo "Warning: google provider split failed — will retry on next run."

echo 'Initializing provider settings...'
/opt/venv/bin/python scripts/init_provider_settings.py

echo 'Initializing priorities...'
/opt/venv/bin/python scripts/init_device_priorities.py

echo 'Seeding admin account...'
/opt/venv/bin/python scripts/init/seed_admin.py

echo 'Initializing series type definitions...'
/opt/venv/bin/python scripts/init/seed_series_types.py

echo 'Initializing archival settings...'
/opt/venv/bin/python scripts/init/seed_archival_settings.py

# Upstream data migrations (idempotent, provider-scoped no-ops for us today;
# TODO upstream removes them ~2026-11/12 — drop here then too).
echo 'Running Ultrahuman body_temperature->skin_temperature relabel...'
/opt/venv/bin/python scripts/data_migrations/relabel_ultrahuman_body_temp_to_skin_temp.py \
    || echo "Warning: Ultrahuman temperature relabel failed — will retry on next run."

echo 'Running Ultrahuman HRV SDNN->RMSSD relabel...'
/opt/venv/bin/python scripts/data_migrations/relabel_ultrahuman_hrv_sdnn_to_rmssd.py \
    || echo "Warning: Ultrahuman HRV relabel failed — will retry on next run."

echo 'Running Whoop strain event_record backfill...'
/opt/venv/bin/python scripts/data_migrations/backfill_whoop_strain_event_record.py \
    || echo "Warning: Whoop strain backfill failed — will retry on next run."
