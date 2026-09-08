"""Bounded LangGraph ReAct workflow with durable checkpoints and HITL."""

import json
from collections.abc import Sequence
from typing import Any, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from src.agent.prompt_loader import load_system_prompt
from src.agent.state import AgentInput, AgentOutput, AgentState

DESTRUCTIVE_TOOLS = {"cancel_reservation", "remove_order_item"}
DESTRUCTIVE_WORDS = {"cancel", "remove", "delete"}
BOOKING_TOOLS = {"check_availability", "create_reservation"}
ANY_SEATING_PHRASES = {"either", "any seating", "anywhere", "no preference", "doesn't matter", "does not matter"}
INDOOR_WORDS = {"indoor", "inside"}
OUTDOOR_WORDS = {"outdoor", "outside"}
SEATING_QUESTION = "Before I check availability, would you prefer indoor or outdoor seating, or is either okay?"


def _last_human_text(messages: Sequence[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content).lower()
    return ""


def _needs_confirmation(state: AgentState) -> bool:
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return False
    destructive = any(call.get("name") in DESTRUCTIVE_TOOLS for call in last.tool_calls)
    explicit = any(word in _last_human_text(state["messages"]) for word in DESTRUCTIVE_WORDS)
    return destructive and not explicit


def _customer_seating(customer_context: str) -> str | None:
    """Return a valid saved seating preference from trusted customer context."""

    try:
        value = json.loads(customer_context).get("preferences", {}).get("seating")
    except (AttributeError, json.JSONDecodeError):
        return None
    return value if value in {"indoor", "outdoor"} else None


def _explicit_seating(messages: Sequence[Any]) -> str | None:
    """Resolve an explicit seating choice from conversation turns."""

    text = " ".join(str(message.content).lower() for message in messages if isinstance(message, HumanMessage))
    if any(phrase in text for phrase in ANY_SEATING_PHRASES):
        return "either"
    if any(word in text for word in OUTDOOR_WORDS):
        return "outdoor"
    if any(word in text for word in INDOOR_WORDS):
        return "indoor"
    return None


def _guard_booking_tools(state: AgentState, response: AIMessage) -> tuple[AIMessage, dict[str, object]]:
    """Block premature booking tools and apply trusted saved seating defaults."""

    booking_calls = [call for call in response.tool_calls if call.get("name") in BOOKING_TOOLS]
    if not booking_calls:
        return response, {}
    explicit = _explicit_seating(state["messages"])
    saved = _customer_seating(state["customer_context"])
    resolved = explicit or saved
    if resolved is None:
        clarification = AIMessage(content=SEATING_QUESTION)
        return clarification, {
            "response": SEATING_QUESTION,
            "booking_location": None,
            "booking_location_resolved": False,
            "missing_booking_fields": ["seating"],
        }
    if resolved in {"indoor", "outdoor"}:
        calls = []
        for call in response.tool_calls:
            updated = dict(call)
            if call.get("name") == "check_availability" and not call.get("args", {}).get("location"):
                updated["args"] = {**call.get("args", {}), "location": resolved}
            calls.append(updated)
        response = response.model_copy(update={"tool_calls": calls})
    return response, {
        "booking_location": None if resolved == "either" else resolved,
        "booking_location_resolved": True,
        "missing_booking_fields": [],
    }


class AgentGraphRunner:
    """Build and invoke one customer-scoped graph using a shared checkpointer."""

    def __init__(
        self,
        model: BaseChatModel,
        tools: list[BaseTool],
        checkpointer: BaseCheckpointSaver[Any],
        max_steps: int,
        max_tool_calls: int = 12,
        max_mutations: int = 6,
    ) -> None:
        self._max_steps = max_steps
        self._max_tool_calls = max_tool_calls
        self._max_mutations = max_mutations
        self._model = model.bind_tools(tools)
        self._graph = self._build_graph(tools, checkpointer)

    def _build_graph(self, tools: list[BaseTool], checkpointer: BaseCheckpointSaver[Any]) -> Any:
        async def retrieve_context(state: AgentState) -> dict[str, object]:
            prompt = f"{load_system_prompt()}\n\n## Customer Context\n{state['customer_context']}"
            return {
                "messages": [SystemMessage(content=prompt, id="system-context")],
                "step_count": 0,
                "tool_call_count": 0,
                "mutation_count": 0,
                "parsing_errors": [],
            }

        async def call_model(state: AgentState) -> dict[str, object]:
            steps = state.get("step_count", 0) + 1
            if steps > self._max_steps:
                fallback = "I couldn't safely complete that request in one turn. Please try a simpler request."
                return {
                    "messages": [AIMessage(content=fallback)],
                    "step_count": steps,
                    "response": fallback,
                }
            response = await self._model.ainvoke(state["messages"])
            guard_state: dict[str, object] = {}
            if isinstance(response, AIMessage):
                response, guard_state = _guard_booking_tools(state, response)
            calls = response.tool_calls if isinstance(response, AIMessage) else []
            tool_call_count = state.get("tool_call_count", 0) + len(calls)
            mutation_tools = {
                "create_reservation",
                "cancel_reservation",
                "add_order_item",
                "remove_order_item",
                "remember_preferences",
            }
            mutation_count = state.get("mutation_count", 0) + sum(call.get("name") in mutation_tools for call in calls)
            if tool_call_count > self._max_tool_calls or mutation_count > self._max_mutations:
                fallback = "I stopped before making more changes because this request exceeded the safe action limit."
                return {
                    "messages": [AIMessage(content=fallback)],
                    "step_count": steps,
                    "tool_call_count": tool_call_count,
                    "mutation_count": mutation_count,
                    "response": fallback,
                }
            return {
                "messages": [response],
                "step_count": steps,
                "tool_call_count": tool_call_count,
                "mutation_count": mutation_count,
                **guard_state,
            }

        async def confirm_action(state: AgentState) -> dict[str, str]:
            answer = interrupt({"question": "Please confirm that you want me to perform that cancellation or removal."})
            return {"confirmation": str(answer).strip().lower()}

        async def decline_action(_: AgentState) -> dict[str, object]:
            message = "Okay, I won't make that cancellation or removal."
            return {"messages": [AIMessage(content=message)], "response": message}

        def route_after_model(state: AgentState) -> str:
            last = state["messages"][-1]
            if state.get("response"):
                return END
            if isinstance(last, AIMessage) and last.tool_calls:
                return "confirm_action" if _needs_confirmation(state) else "execute_tools"
            return END

        def route_after_confirmation(state: AgentState) -> str:
            accepted = state.get("confirmation") in {"yes", "y", "confirm", "confirmed", "please do"}
            return "execute_tools" if accepted else "decline_action"

        builder = StateGraph(AgentState, input_schema=AgentInput, output_schema=AgentOutput)
        builder.add_node("retrieve_context", retrieve_context)
        builder.add_node("call_model", call_model)
        builder.add_node("confirm_action", confirm_action)
        builder.add_node("execute_tools", ToolNode(tools, handle_tool_errors=True))
        builder.add_node("decline_action", cast(Any, decline_action))
        builder.add_edge(START, "retrieve_context")
        builder.add_edge("retrieve_context", "call_model")
        builder.add_conditional_edges("call_model", route_after_model)
        builder.add_conditional_edges("confirm_action", route_after_confirmation)
        builder.add_edge("execute_tools", "call_model")
        builder.add_edge("decline_action", END)
        return builder.compile(checkpointer=checkpointer)

    async def run(self, session_id: str, message: str, customer_context: str) -> tuple[str, str]:
        config = {"configurable": {"thread_id": session_id}, "recursion_limit": self._max_steps * 3}
        snapshot = await self._graph.aget_state(config)
        if snapshot.next and "confirm_action" in snapshot.next:
            result = await self._graph.ainvoke(Command(resume=message), config=config)
        else:
            result = await self._graph.ainvoke(
                {"messages": [HumanMessage(content=message)], "customer_context": customer_context}, config=config
            )
        next_snapshot = await self._graph.aget_state(config)
        if next_snapshot.next:
            question = "Please confirm that you want me to perform that cancellation or removal."
            return question, "needs_input"
        response = result.get("response")
        if not response:
            last = result["messages"][-1]
            response = str(last.content)
        return response, "completed"
