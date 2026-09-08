"""API boundary, routes, middleware, settings, and redaction tests."""

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi import Response as FastApiResponse
from fastapi.testclient import TestClient

from src.api import register_exception_handlers
from src.middleware.request_context import RequestContextMiddleware
from src.models.api import (
    MessageRequest,
    MessageResponse,
    ReadyResponse,
    SessionCustomer,
    SessionResponse,
    StartSessionRequest,
    StreamEvent,
)
from src.routes.health import health, ready
from src.routes.sessions import _encode_sse, send_message, start_session
from src.routes.ui import frontend
from src.settings import Settings
from src.utils.exceptions import AppError
from src.utils.logger import redact


def test_app_error_handler_and_security_headers() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise AppError("EXPECTED", "Safe message", 409)

    response = TestClient(app).get("/boom")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EXPECTED"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert response.headers["x-trace-id"]


def test_validation_handler_hides_field_details() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    response = TestClient(app).get("/items/not-an-int")
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Request validation failed."


def test_sse_encoder_uses_standard_event_framing() -> None:
    frame = _encode_sse(StreamEvent(event="delta", data={"text": "Hello"}))
    assert frame == 'event: delta\ndata: {"text":"Hello"}\n\n'


def test_redaction_recurses_through_sensitive_values() -> None:
    value = {"email": "priya@example.com", "note": "Call +91 98765 43210", "token": "secret", "items": ["safe"]}
    redacted = redact(value)
    assert redacted["email"] == "[EMAIL]"
    assert redacted["note"] == "Call [PHONE]"
    assert redacted["token"] == "[" + "REDACTED]"
    assert redacted["items"] == ["safe"]


def test_settings_normalize_upstream_url_and_validate_timezone() -> None:
    settings = Settings(groq_api_key="test", restaurant_api_base_url="http://localhost:8000/")
    assert settings.restaurant_api_base_url == "http://localhost:8000"
    assert settings.restaurant_timezone == "Asia/Kolkata"


@pytest.mark.asyncio
async def test_frontend_returns_local_test_client() -> None:
    response = await frontend()
    assert response.media_type == "text/html"
    assert str(response.path).endswith("index.html")
    content = response.path.read_text(encoding="utf-8")
    assert 'id="root"' in content or "Suggested messages" in content


class DatabaseContext:
    async def __aenter__(self) -> "DatabaseContext":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, _: object) -> None:
        return None


@pytest.mark.asyncio
async def test_health_routes_report_dependencies() -> None:
    assert (await health()).status == "ok"

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test") as client:
        state = SimpleNamespace(database_session_factory=lambda: DatabaseContext(), restaurant_http_client=client)
        response = FastApiResponse()
        result = await ready(SimpleNamespace(app=SimpleNamespace(state=state)), response)  # type: ignore[arg-type]
    assert result == ReadyResponse(status="ready")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_session_route_functions_delegate_to_services() -> None:
    session_id = uuid4()
    session_response = SessionResponse(
        session_id=session_id,
        customer=SessionCustomer(id=1, name="Priya", is_new=False),
        created_at="2030-01-01T00:00:00Z",
    )
    message_response = MessageResponse(
        session_id=session_id,
        client_message_id="m1",
        message="Done",
        status="completed",
        trace_id=uuid4(),
    )

    class SessionStub:
        async def start(self, _: object) -> SessionResponse:
            return session_response

    class ConversationStub:
        async def send(self, _: object, __: object) -> MessageResponse:
            return message_response

    started = await start_session(
        StartSessionRequest(customer={"phone": "+91-1"}),  # type: ignore[arg-type]
        SessionStub(),  # type: ignore[arg-type]
    )
    sent = await send_message(
        session_id,
        MessageRequest(client_message_id="m1", message="Hello"),
        ConversationStub(),  # type: ignore[arg-type]
    )
    assert started == session_response
    assert sent == message_response
