from app.config import settings
from app.integrations.task_dispatcher import RegisteredTask, TaskDispatchHandle, dispatch_task
from app.services.task_payload_storage import store_task_payload


def enqueue_sdk_upload(
    *,
    content: str,
    content_type: str,
    user_id: str,
    provider: str,
    batch_id: str | None = None,
) -> TaskDispatchHandle:
    payload_bytes = content.encode("utf-8")
    if _should_offload_payload(len(payload_bytes)):
        payload_ref = store_task_payload(
            payload_bytes,
            content_type=content_type,
            prefix=f"sdk/{provider}",
            filename=f"{batch_id or user_id}.json",
        )
        return dispatch_task(
            RegisteredTask.PROCESS_SDK_UPLOAD_REFERENCE,
            kwargs={
                "payload_ref": payload_ref,
                "content_type": content_type,
                "user_id": user_id,
                "provider": provider,
                "batch_id": batch_id,
            },
        )

    return dispatch_task(
        RegisteredTask.PROCESS_SDK_UPLOAD,
        kwargs={
            "content": content,
            "content_type": content_type,
            "user_id": user_id,
            "provider": provider,
            "batch_id": batch_id,
        },
    )


def enqueue_xml_upload(
    *,
    file_contents: bytes,
    filename: str,
    user_id: str,
) -> TaskDispatchHandle:
    if _should_offload_payload(len(file_contents)):
        payload_ref = store_task_payload(
            file_contents,
            content_type="application/xml",
            prefix="xml/direct",
            filename=filename,
        )
        return dispatch_task(
            RegisteredTask.PROCESS_XML_UPLOAD_REFERENCE,
            kwargs={
                "payload_ref": payload_ref,
                "filename": filename,
                "user_id": user_id,
            },
        )

    return dispatch_task(
        RegisteredTask.PROCESS_XML_UPLOAD,
        kwargs={
            "file_contents": file_contents,
            "filename": filename,
            "user_id": user_id,
        },
    )


def _should_offload_payload(payload_size_bytes: int) -> bool:
    if settings.task_dispatch_backend != "cloud_tasks":
        return False

    if settings.task_payload_storage_backend != "inline":
        return True

    if payload_size_bytes > settings.task_payload_inline_max_bytes:
        raise ValueError(
            "Payload is too large for inline Cloud Tasks dispatch. Configure TASK_PAYLOAD_STORAGE_BACKEND=gcs."
        )

    return False
