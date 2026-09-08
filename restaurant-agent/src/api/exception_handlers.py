"""Global exception handlers with stable public envelopes."""

import logging
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.utils.exceptions import AppError, error_codes
from src.utils.exceptions.error_responses import ErrorDetail, ErrorResponse
from src.utils.logger import log_event

logger = logging.getLogger(__name__)


def _trace_id(request: Request) -> UUID:
    return getattr(request.state, "trace_id", uuid4())


def _response(status_code: int, detail: ErrorDetail) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=ErrorResponse(error=detail).model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        trace_id = _trace_id(request)
        log_event(logger, "application_error", trace_id=trace_id, path=request.url.path, error_code=exc.code)
        return _response(
            exc.status_code,
            ErrorDetail(code=exc.code, message=exc.message, trace_id=trace_id, retryable=exc.retryable),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        trace_id = _trace_id(request)
        log_event(logger, "validation_error", trace_id=trace_id, path=request.url.path)
        return _response(
            422,
            ErrorDetail(code=error_codes.VALIDATION_ERROR, message="Request validation failed.", trace_id=trace_id),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        trace_id = _trace_id(request)
        logger.exception("Unhandled error trace_id=%s path=%s", trace_id, request.url.path)
        return _response(
            500,
            ErrorDetail(
                code=error_codes.INTERNAL_ERROR,
                message="An unexpected error occurred.",
                trace_id=trace_id,
                retryable=True,
            ),
        )
