from typing import Any, cast

from celery import shared_task

from app.integrations.celery.tasks.process_sdk_upload_task import process_sdk_upload
from app.services.task_payload_storage import TaskPayloadReference, delete_task_payload, load_task_payload


@shared_task(queue="sdk_sync")
def process_sdk_upload_reference(
    payload_reference: dict[str, Any],
    content_type: str,
    user_id: str,
    provider: str,
    batch_id: str | None = None,
    payload_ref: str | None = None,
) -> dict[str, int | str]:
    """Load an offloaded SDK payload from task-payload storage and process it.

    ``payload_ref`` is upstream's *separate* S3-offload marker: the dispatcher
    forwards every kwarg of the base task when it swaps in this reference
    variant, so this signature must stay a superset of ``process_sdk_upload``'s
    (see test_reference_tasks_accept_base_task_kwargs). In practice the two
    offload paths are mutually exclusive - upstream's sets ``content=None``,
    which makes the dispatcher skip this swap entirely - so it is passed
    straight through rather than interpreted here.
    """
    reference = cast(TaskPayloadReference, payload_reference)
    try:
        content = load_task_payload(reference).decode("utf-8")
        return process_sdk_upload(
            content=content,
            content_type=content_type,
            user_id=user_id,
            provider=provider,
            batch_id=batch_id,
            payload_ref=payload_ref,
        )
    finally:
        delete_task_payload(reference)
