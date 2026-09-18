"""FastAPI error handlers.

Conforms to Problem Statement section 6.1:
- 200 success
- 400 malformed JSON or structurally invalid request
- 422 semantic validation error (allowed alternative)
- 500 controlled internal error; never expose secrets or stack traces
"""

import json
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.security import safe_headers

log = logging.getLogger(__name__)


def install(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        body_bytes = await request.body()
        structurally_valid = False
        try:
            json.loads(body_bytes)
            structurally_valid = True
        except Exception:
            structurally_valid = False
        code = 400 if not structurally_valid else 422
        # Do not echo full request body in response — only structural hints
        return JSONResponse(
            status_code=code,
            content={
                "detail": "invalid_request",
                "structurally_valid": structurally_valid,
                "errors": [
                    {"loc": list(e.get("loc", [])), "msg": e.get("msg", "")}
                    for e in exc.errors()
                ],
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail if isinstance(exc.detail, str) else "error"},
        )

    @app.exception_handler(Exception)
    async def _internal(request: Request, exc: Exception):
        # Log safely (no headers, no secrets)
        log.error(
            "internal_error path=%s method=%s type=%s msg=%s",
            request.url.path,
            request.method,
            type(exc).__name__,
            str(exc)[:200],
        )
        return JSONResponse(status_code=500, content={"detail": "internal_error"})
