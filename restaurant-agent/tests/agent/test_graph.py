"""Offline end-to-end tests for the LangGraph loop and interrupt path."""

from datetime import datetime, timedelta
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import Field

from src.agent.graph import AgentGraphRunner, _guard_booking_tools, _needs_confirmation
from src.agent.prompt_loader import load_system_prompt
from src.models.domain import Reservation
from src.tools import build_restaurant_tools


class StubChatModel(BaseChatModel):
    responses: list[AIMessage] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "stub"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "StubChatModel":
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])


class CancellationClient:
    def __init__(self) -> None:
        self.cancelled = False

    async def list_reservations(self, customer_id: int, status: str | None = None) -> list[Reservation]:
        return [
            Reservation(
                id=4,
                customer_id=customer_id,
                table_id=7,
                slot_datetime=datetime.now() + timedelta(days=1),
                party_size=3,
                special_requests=None,
                status="confirmed",
                created_at=datetime.now(),
            )
        ]

    async def cancel_reservation(self, reservation_id: int) -> Reservation:
        self.cancelled = True
        item = (await self.list_reservations(1))[0]
        return item.model_copy(update={"status": "cancelled"})


@pytest.mark.asyncio
async def test_graph_returns_plain_model_response() -> None:
    model = StubChatModel(responses=[AIMessage(content="We have samosas.")])
    runner = AgentGraphRunner(model, [], InMemorySaver(), max_steps=8)
    response, status = await runner.run("session-1", "What starters do you have?", "name=Priya")
    assert response == "We have samosas."
    assert status == "completed"


@pytest.mark.asyncio
async def test_inferred_destructive_action_interrupts_and_resumes() -> None:
    client = CancellationClient()
    model = StubChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "cancel_reservation", "args": {"reservation_id": 4}, "id": "call-1"}],
            ),
            AIMessage(content="Reservation 4 is cancelled."),
        ]
    )
    tools = build_restaurant_tools(client, 1)  # type: ignore[arg-type]
    runner = AgentGraphRunner(model, tools, InMemorySaver(), max_steps=8)
    question, status = await runner.run("session-hitl", "Do what we discussed.", "name=Priya")
    assert status == "needs_input"
    assert "confirm" in question.lower()
    assert client.cancelled is False

    response, status = await runner.run("session-hitl", "yes", "name=Priya")
    assert status == "completed"
    assert response == "Reservation 4 is cancelled."
    assert client.cancelled is True


def test_confirmation_detection_requires_destructive_tool_without_explicit_verb() -> None:
    inferred = {
        "messages": [
            {"role": "user", "content": "Do that."},
            AIMessage(
                content="",
                tool_calls=[{"name": "cancel_reservation", "args": {"reservation_id": 4}, "id": "1"}],
            ),
        ]
    }
    explicit = {
        "messages": [
            {"role": "user", "content": "Cancel reservation 4."},
            AIMessage(
                content="",
                tool_calls=[{"name": "cancel_reservation", "args": {"reservation_id": 4}, "id": "2"}],
            ),
        ]
    }
    inferred["messages"][0] = HumanMessage(content="Do that.")
    explicit["messages"][0] = HumanMessage(content="Cancel reservation 4.")
    assert _needs_confirmation(inferred) is True  # type: ignore[arg-type]
    assert _needs_confirmation(explicit) is False  # type: ignore[arg-type]


def test_prompt_contains_required_stable_rules() -> None:
    prompt = load_system_prompt()
    assert "RRA-001" in prompt
    assert "RRA-007" in prompt
    assert "RRA-008" in prompt
    assert "Customer Context" not in prompt


@pytest.mark.asyncio
async def test_new_customer_cannot_book_before_seating_is_resolved() -> None:
    model = StubChatModel(
        responses=[
            AIMessage(content="What date and seating would you like?"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "check_availability",
                        "args": {"slot_datetime": "2030-01-10T19:30:00", "party_size": 4},
                        "id": "availability-1",
                    }
                ],
            ),
        ]
    )
    runner = AgentGraphRunner(model, [], InMemorySaver(), max_steps=8)
    context = '{"customer_id":9,"name":"New customer","preferences":{}}'

    await runner.run("new-customer-booking", "Book a table for four.", context)
    response, status = await runner.run("new-customer-booking", "January 10 at 7:30 PM.", context)

    assert status == "completed"
    assert "indoor or outdoor" in response


def test_saved_seating_is_injected_into_availability_call() -> None:
    response = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "check_availability",
                "args": {"slot_datetime": "2030-01-10T19:30:00", "party_size": 4},
                "id": "availability-2",
            }
        ],
    )
    guarded, updates = _guard_booking_tools(
        {
            "messages": [HumanMessage(content="Book for four on January 10 at 7:30 PM")],
            "customer_context": '{"preferences":{"seating":"outdoor"}}',
        },  # type: ignore[arg-type]
        response,
    )

    assert guarded.tool_calls[0]["args"]["location"] == "outdoor"
    assert updates["booking_location_resolved"] is True
