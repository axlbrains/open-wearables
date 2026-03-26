#!/bin/bash
set -e -x

/root_project/.venv/bin/celery -A app.main:celery_app worker --loglevel=info --pool=threads -Q default,sdk_sync
