#!/bin/bash
set -e -x

# Explicit /opt/venv paths, not `uv run`: the venv lives at /opt/venv (Dockerfile),
# and historical /root_project/.venv references silently broke the init job (#22).

echo "Starting I/O worker..."
/opt/venv/bin/celery -A app.main:celery_app worker --loglevel=info --pool=threads -Q default,sdk_sync,garmin_sync,webhook_sync -n io@%h &

echo "Starting CPU worker..."
/opt/venv/bin/celery -A app.main:celery_app worker --loglevel=info --pool=prefork --concurrency=2 -Q xml_sync -n cpu@%h
