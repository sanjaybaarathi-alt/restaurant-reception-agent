"""Service tests with no database or LLM dependency."""

from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.models.api import CustomerIdentity, MessageRequest, StartSessionRequest
from src.models.domain import Customer
from src.services.conversation_service import ConversationService
from src.services.session_service import SessionService
from src.utils.exceptions import AppError


def customer(customer_id: int = 1) -> Customer:
    return Customer(
        id=customer_id,
        name="Priya",
        phone="+91-9876543210",
        email="priya@example.com",
        preferences={"seating": "outdoor"},
        created_at=datetime.now(),
    )


class FakeRestaurantClient:
    def __init__(self, found: Customer | None = None) -> None:
        self.found = found
        self.created = False

    async def lookup_customer(self, **_: object) -> Customer | None:
        return self.found

    async def create_customer(self, **_: object) -> Customer:
        self.created = True
        return customer()

    async def get_customer(self, customer_id: int) -> Customer:
        return customer(customer_id)


class FakeRepository:
    def __init__(self) -> None:
        self.session = None
        self.messages: dict[tuple[object, str], object] = {}

    async def create(self, session: object) -> object:
        self.session = session
        return session

    async def get(self, session_id: object) -> object | None:
        return self.session

    async def get_message(self, session_id: object, client_message_id: str) -> object | None:
        return self.messages.get((session_id, client_message_id))

    async def begin_message(self, session_id: object, client_message_id: str, request_hash: str) -> object:
        record = SimpleNamespace(request_hash=request_hash, response=None, status="processing")
        self.messages[(session_id, client_message_id)] = record
        return record

    async def complete_message(self, record: object, response: dict[str, object]) -> None:
        record.response = response

    async def fail_message(self, record: object, response: dict[str, object]) -> None:
        record.response = response


class FakeRunner:
    async def run(self, session_id: str, message: str, context: str) -> tuple[str, str]:
        assert "preferences" in context
        return f"Handled: {message}", "completed"


@pytest.mark.asyncio
async def test_known_customer_starts_session_without_creation() -> None:
    repository = FakeRepository()
    client = FakeRestaurantClient(customer())
    response = await SessionService(repository, client).start(  # type: ignore[arg-type]
        StartSessionRequest(customer=CustomerIdentity(phone="+91-9876543210"))
    )
    assert response.customer.name == "Priya"
    assert response.customer.is_new is False
    assert client.created is False


@pytest.mark.asyncio
async def test_unknown_customer_requires_name() -> None:
    with pytest.raises(AppError) as error:
        await SessionService(FakeRepository(), FakeRestaurantClient()).start(  # type: ignore[arg-type]
            StartSessionRequest(customer=CustomerIdentity(phone="+91-0"))
        )
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_conversation_is_idempotent() -> None:
    session_id = uuid4()
    repository = FakeRepository()
    repository.session = SimpleNamespace(id=session_id, customer_id=1, customer_name="Priya")
    client = FakeRestaurantClient(customer())
    session_service = SessionService(repository, client)  # type: ignore[arg-type]
    service = ConversationService(repository, session_service, client, lambda *_: FakeRunner())  # type: ignore[arg-type]
    request = MessageRequest(client_message_id="msg-1", message="What did I order last time?")
    first = await service.send(session_id, request)
    second = await service.send(session_id, request)
    assert first == second
    assert first.message.startswith("Handled")


@pytest.mark.asyncio
async def test_conversation_stream_emits_progress_deltas_and_canonical_completion() -> None:
    session_id = uuid4()
    repository = FakeRepository()
    repository.session = SimpleNamespace(id=session_id, customer_id=1, customer_name="Priya")
    client = FakeRestaurantClient(customer())
    service = ConversationService(
        repository,
        SessionService(repository, client),  # type: ignore[arg-type]
        client,
        lambda *_: FakeRunner(),  # type: ignore[arg-type]
    )

    events = [
        event
        async for event in service.stream(
            session_id, MessageRequest(client_message_id="stream-1", message="Show the menu")
        )
    ]

    assert [event.event for event in events[:3]] == ["status", "status", "status"]
    assert "".join(event.data["text"] for event in events if event.event == "delta") == "Handled: Show the menu"
    assert events[-1].event == "complete"
    assert events[-1].data["client_message_id"] == "stream-1"


@pytest.mark.asyncio
async def test_conversation_stream_returns_safe_error_event() -> None:
    service = ConversationService(
        FakeRepository(),
        SessionService(FakeRepository(), FakeRestaurantClient()),  # type: ignore[arg-type]
        FakeRestaurantClient(),
        lambda *_: FakeRunner(),  # type: ignore[arg-type]
    )

    events = [
        event
        async for event in service.stream(uuid4(), MessageRequest(client_message_id="stream-error", message="Hello"))
    ]

    assert events[-1].event == "error"
    assert events[-1].data["error"]["code"] == "SESSION_NOT_FOUND"
