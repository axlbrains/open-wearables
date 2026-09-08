import base64
import importlib
import json
from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.integrations import task_dispatcher
from app.integrations.task_dispatcher import (
    RegisteredTask,
    TaskDispatchBackend,
    deserialize_payload,
    dispatch_task,
    serialize_payload,
)


@pytest.mark.asyncio
async def test_serialize_payload_round_trips_bytes() -> None:
    payload = {
        "file_contents": b"<xml>payload</xml>",
        "items": [1, {"binary": b"abc"}],
    }

    serialized = serialize_payload(payload)

    expected_bytes = base64.b64encode(b"<xml>payload</xml>").decode("ascii")
    assert serialized["file_contents"] == {"__open_wearables_bytes__": expected_bytes}
    assert deserialize_payload(serialized) == payload


def test_dispatch_task_uses_celery_send_task(monkeypatch: pytest.MonkeyPatch) -> None:
    send_task_mock = MagicMock()
    send_task_mock.return_value.id = "celery-task-id"

    monkeypatch.setattr(task_dispatcher.current_celery_app, "send_task", send_task_mock)
    monkeypatch.setattr(settings, "task_dispatch_backend", TaskDispatchBackend.CELERY.value)

    handle = dispatch_task(
        RegisteredTask.SYNC_VENDOR_DATA,
        kwargs={"user_id": "user-123"},
    )

    assert handle.id == "celery-task-id"
    assert handle.backend is TaskDispatchBackend.CELERY
    send_task_mock.assert_called_once_with(
        "app.integrations.celery.tasks.sync_vendor_data_task.sync_vendor_data",
        args=[],
        kwargs={"user_id": "user-123"},
        countdown=None,
        queue="default",
        task_id=None,
    )


def test_dispatch_task_uses_cloud_tasks_http_api(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata_response = MagicMock()
    metadata_response.json.return_value = {"access_token": "metadata-token"}
    metadata_response.raise_for_status.return_value = None

    cloud_tasks_response = MagicMock()
    cloud_tasks_response.json.return_value = {"name": "projects/test/locations/eu/queues/default/tasks/123"}
    cloud_tasks_response.raise_for_status.return_value = None

    httpx_get_mock = MagicMock(return_value=metadata_response)
    httpx_post_mock = MagicMock(return_value=cloud_tasks_response)

    monkeypatch.setattr(task_dispatcher.httpx, "get", httpx_get_mock)
    monkeypatch.setattr(task_dispatcher.httpx, "post", httpx_post_mock)
    monkeypatch.setattr(settings, "task_dispatch_backend", TaskDispatchBackend.CLOUD_TASKS.value)
    monkeypatch.setattr(settings, "task_dispatcher_gcp_project_id", "test-project")
    monkeypatch.setattr(settings, "task_dispatcher_gcp_location", "europe-west1")
    monkeypatch.setattr(settings, "task_dispatcher_worker_base_url", "https://worker.example.run.app")
    monkeypatch.setattr(settings, "task_dispatcher_service_account_email", "api@test-project.iam.gserviceaccount.com")
    monkeypatch.setattr(settings, "task_dispatcher_audience", "https://worker.example.run.app")
    monkeypatch.setattr(settings, "task_dispatcher_default_queue_name", "ow-default")
    monkeypatch.setattr(settings, "task_dispatcher_sdk_sync_queue_name", "ow-sdk")
    monkeypatch.setattr(settings, "task_dispatcher_garmin_backfill_queue_name", "ow-garmin")

    handle = dispatch_task(
        RegisteredTask.PROCESS_XML_UPLOAD,
        kwargs={
            "file_contents": b"<xml/>",
            "filename": "payload.xml",
            "user_id": "user-123",
        },
        countdown=30,
    )

    assert handle.backend is TaskDispatchBackend.CLOUD_TASKS
    assert handle.id == "projects/test/locations/eu/queues/default/tasks/123"

    httpx_get_mock.assert_called_once()
    httpx_post_mock.assert_called_once()

    request_url = httpx_post_mock.call_args.args[0]
    request_json = httpx_post_mock.call_args.kwargs["json"]
    request_headers = httpx_post_mock.call_args.kwargs["headers"]

    assert request_url.endswith("/projects/test-project/locations/europe-west1/queues/ow-default/tasks")
    assert request_headers["Authorization"] == "Bearer metadata-token"
    http_request = request_json["task"]["httpRequest"]
    assert http_request["url"] == "https://worker.example.run.app/api/v1/internal/tasks/process_xml_upload"
    assert http_request["oidcToken"]["serviceAccountEmail"] == "api@test-project.iam.gserviceaccount.com"

    raw_body = base64.b64decode(request_json["task"]["httpRequest"]["body"]).decode("utf-8")
    decoded = json.loads(raw_body)
    assert decoded["kwargs"]["filename"] == "payload.xml"
    assert decoded["kwargs"]["file_contents"]["__open_wearables_bytes__"] == base64.b64encode(b"<xml/>").decode("ascii")


class TestReferenceTaskSignatureParity:
    """The dispatcher swaps a large-payload task for its ``*_reference`` variant and
    forwards every other kwarg unchanged. So each reference task must accept every
    kwarg its base task accepts, minus the offloaded one.

    Regression for the 2026-09-08 prod incident: upstream added ``payload_ref`` to
    process_sdk_upload, the reference sibling was not updated, and every SDK batch
    over task_payload_inline_max_bytes died with TypeError and was dropped after
    Cloud Tasks exhausted its retries.
    """

    def test_reference_tasks_accept_base_task_kwargs(self) -> None:
        import inspect

        from app.integrations.task_dispatcher import _OFFLOAD_MAP, TASK_DEFINITIONS

        def _params(task_key: object) -> tuple[set[str], str]:
            definition = TASK_DEFINITIONS[task_key]  # ty:ignore[invalid-argument-type]
            module_path, _, attr = definition.callable_path.rpartition(".")
            module = importlib.import_module(module_path)
            fn = getattr(module, attr)
            fn = getattr(fn, "__wrapped__", fn)  # unwrap @idempotent / celery task
            return set(inspect.signature(fn).parameters), definition.callable_path

        for base_key, (payload_key, ref_key, *_rest) in _OFFLOAD_MAP.items():
            base_params, base_path = _params(base_key)
            ref_params, ref_path = _params(ref_key)
            forwarded = base_params - {payload_key}
            missing = forwarded - ref_params
            assert not missing, (
                f"{ref_path} cannot accept kwargs forwarded from {base_path}: {sorted(missing)}. "
                "The dispatcher passes them through verbatim, so this is a runtime TypeError."
            )
