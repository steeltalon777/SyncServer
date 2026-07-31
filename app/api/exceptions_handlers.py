from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.operation_submit_errors import OperationSubmitError


async def operation_submit_error_handler(request: Request, exc: OperationSubmitError) -> JSONResponse:
    envelope = exc.to_envelope(
        instance=str(request.url.path),
        trace_id=request.headers.get("X-Request-Id"),
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=envelope.model_dump(exclude_none=True),
    )
