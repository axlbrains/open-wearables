import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
from pydantic import BaseModel, Field

from app.config import settings
from app.integrations.task_dispatcher import (
    RegisteredTask,
    deserialize_payload,
    invoke_registered_task,
)
from app.utils.structured_logging import log_structured

logger = logging.getLogger(__name__)

_google_request = GoogleAuthRequest()


def verify_task_caller(authorization: Annotated[str | None, Header()] = None) -> None:
    """Accept only Google-signed OIDC tokens from the allowed service accounts.

    Off when INTERNAL_TASK_OIDC_AUDIENCE is unset (Cloud Run keeps the worker behind
    internal ingress and IAM instead).
    """
    audience = settings.internal_task_oidc_audience
    if not audience:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        claims = id_token.verify_oauth2_token(authorization.removeprefix("Bearer "), _google_request, audience)
    except ValueError as exc:
        log_structured(
            logger, "warning", "Rejected internal task token", action="internal_task_auth_reject", reason=str(exc)
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    email = claims.get("email")
    if not claims.get("email_verified") or email not in settings.internal_task_allowed_service_accounts:
        log_structured(
            logger, "warning", "Rejected internal task caller", action="internal_task_auth_reject", email=email
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Caller not allowed")


router = APIRouter(prefix="/internal/tasks", dependencies=[Depends(verify_task_caller)])


class TaskInvocationPayload(BaseModel):
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


@router.post("/{task_key}")
async def run_internal_task(
    task_key: RegisteredTask,
    payload: TaskInvocationPayload,
) -> dict[str, Any]:
    args = [deserialize_payload(item) for item in payload.args]
    kwargs = {key: deserialize_payload(value) for key, value in payload.kwargs.items()}
    result = invoke_registered_task(task_key, args=args, kwargs=kwargs)
    return {
        "status": "ok",
        "task": task_key.value,
        "result": result,
    }
