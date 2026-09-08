"""Liveness and readiness endpoints."""

import logging

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import select

from src.models.api import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
@router.get("/healthz", response_model=HealthResponse, include_in_schema=False)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=ReadyResponse)
@router.get("/readyz", response_model=ReadyResponse, include_in_schema=False)
async def ready(request: Request, response: Response) -> ReadyResponse:
    database_ok = False
    upstream_ok = False
    try:
        async with request.app.state.database_session_factory() as database_session:
            await database_session.execute(select(1))
            database_ok = True
        upstream_response = await request.app.state.restaurant_http_client.get("/health")
        upstream_ok = upstream_response.status_code == 200
    except Exception as exc:
        logger.warning("Readiness dependency check failed: %s", type(exc).__name__)
    if not (database_ok and upstream_ok):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyResponse(status="not_ready")
    return ReadyResponse(status="ready")
