"""Task dispatcher abstraction.

A single entry point for dispatching background tasks. All call sites
should use :func:`dispatch_task` instead of calling ``task.delay()`` or
``task.apply_async()`` directly.

Benefits:

- **One call site pattern** for every background task, easy to grep and
  mock.
- **A registry enum** (:class:`RegisteredTask`) as the single source of
  truth for what background tasks exist in the project.
- **An extension point** for alternative dispatch backends (e.g. cloud
  task queues, Dramatiq, SQS) — downstream forks can wrap or monkey-patch
  this function without touching call sites.

The default (and currently the only bundled) backend is Celery. Behavior
is byte-identical to the previous ``task.apply_async(...)`` calls: the
registered task name is routed through ``task_routes`` on the current
Celery app, so per-task queue routing (e.g. ``sdk_sync``) keeps working.
"""

from enum import Enum
from typing import Any

import celery
from celery.result import AsyncResult


class RegisteredTask(str, Enum):
    """All background tasks dispatched via :func:`dispatch_task`.

    The string values are the fully-qualified Celery task names as
    registered by ``@shared_task``. Adding a new task means adding an
    entry here and using it at the call site; the enum is the single
    place to audit what runs in the background.
    """

    # One-shot uploads / ingests
    PROCESS_AWS_UPLOAD = "app.integrations.celery.tasks.process_aws_upload_task.process_aws_upload"
    PROCESS_SDK_UPLOAD = "app.integrations.celery.tasks.process_sdk_upload_task.process_sdk_upload"
    PROCESS_XML_UPLOAD = "app.integrations.celery.tasks.process_xml_upload_task.process_xml_upload"

    # Notifications
    SEND_INVITATION_EMAIL = "app.integrations.celery.tasks.send_email_task.send_invitation_email_task"

    # Recurring / on-demand sync
    SYNC_VENDOR_DATA = "app.integrations.celery.tasks.sync_vendor_data_task.sync_vendor_data"
    FINALIZE_STALE_SLEEPS = "app.integrations.celery.tasks.finalize_stale_sleep_task.finalize_stale_sleeps"
    RUN_DAILY_ARCHIVAL = "app.integrations.celery.tasks.archival_task.run_daily_archival"

    # Garmin backfill chain (webhook-driven, multi-step)
    START_GARMIN_FULL_BACKFILL = "app.integrations.celery.tasks.garmin_backfill_task.start_full_backfill"
    TRIGGER_GARMIN_BACKFILL_FOR_TYPE = (
        "app.integrations.celery.tasks.garmin_backfill_trigger.trigger_backfill_for_type"
    )
    CHECK_GARMIN_TRIGGERED_TIMEOUT = (
        "app.integrations.celery.tasks.garmin_backfill_timeout.check_triggered_timeout"
    )
    TRIGGER_GARMIN_NEXT_PENDING_TYPE = (
        "app.integrations.celery.tasks.garmin_backfill_task.trigger_next_pending_type"
    )


def dispatch_task(
    task: RegisteredTask,
    *,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    countdown: int | None = None,
) -> AsyncResult:
    """Dispatch a background task to the configured task backend.

    Behaviorally equivalent to
    ``celery_task.apply_async(args=args, kwargs=kwargs, countdown=countdown)``
    for the corresponding registered task, with routing (queue selection,
    retries, etc.) inherited from Celery configuration.

    Args:
        task: The :class:`RegisteredTask` member identifying which task
            to run.
        args: Positional arguments passed to the task.
        kwargs: Keyword arguments passed to the task.
        countdown: Delay in seconds before the task is executed.

    Returns:
        The :class:`celery.result.AsyncResult` returned by Celery's
        ``send_task``.
    """
    # Resolve the current Celery app lazily on each call. This lets tests
    # patch ``celery.current_app`` via conftest autouse fixtures without
    # having to hold on to a stale reference captured at import time.
    return celery.current_app.send_task(
        task.value,
        args=args or [],
        kwargs=kwargs or {},
        countdown=countdown,
    )
