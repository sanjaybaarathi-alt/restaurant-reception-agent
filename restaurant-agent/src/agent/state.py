"""Typed state and I/O contracts for the LangGraph workflow."""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentInput(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    customer_context: str


class AgentOutput(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    response: str


class AgentState(AgentInput, total=False):
    step_count: int
    tool_call_count: int
    mutation_count: int
    parsing_errors: list[str]
    response: str
    confirmation: str
    booking_location: str | None
    booking_location_resolved: bool
    missing_booking_fields: list[str]
