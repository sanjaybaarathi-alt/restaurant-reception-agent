"""Idempotent orchestration of one conversational turn."""

import hashlib
import json
from collections.abc import AsyncGenerator
from typing import Literal, Protocol, cast
from uuid import UUID, uuid4

from src.agent import AgentGraphRunner
from src.client import RestaurantApiClient
from src.models.api import MessageRequest, MessageResponse, StreamEvent, Usage
from src.repositories import SessionRepository
from src.repositories.schema import SessionRecord
from src.services.session_service import SessionService
from src.utils.exceptions import AppError, error_codes


class RunnerFactory(Protocol):
    def __call__(self, restaurant_client: RestaurantApiClient, customer_id: int) -> AgentGraphRunner: ...


class ConversationService:
    def __init__(
        self,
        repository: SessionRepository,
        session_service: SessionService,
        restaurant_client: RestaurantApiClient,
        runner_factory: RunnerFactory,
    ) -> None:
        self._repository = repository
        self._session_service = session_service
        self._restaurant_client = restaurant_client
        self._runner_factory = runner_factory

    async def send(self, session_id: UUID, request: MessageRequest) -> MessageResponse:
        session = await self._session_service.require_session(session_id)
        request_hash = hashlib.sha256(request.message.encode("utf-8")).hexdigest()
        existing = await self._repository.get_message(session_id, request.client_message_id)
        if existing:
            if existing.request_hash != request_hash:
                raise AppError(
                    error_codes.MESSAGE_CONFLICT,
                    "That client_message_id was already used with different content.",
                    409,
                )
            if existing.response:
                return MessageResponse.model_validate(existing.response)
            raise AppError(
                error_codes.MESSAGE_CONFLICT,
                "That message is already being processed. Retry shortly.",
                409,
                True,
            )
        record = await self._repository.begin_message(session_id, request.client_message_id, request_hash)
        trace_id = uuid4()
        try:
            context = await self._customer_context(session)
            runner = self._runner_factory(self._restaurant_client, session.customer_id)
            text, status = await runner.run(str(session_id), request.message, context)
            response = MessageResponse(
                session_id=session_id,
                client_message_id=request.client_message_id,
                message=text,
                status=cast(Literal["completed", "needs_input", "failed"], status),
                trace_id=trace_id,
                usage=Usage(),
            )
            await self._repository.complete_message(record, response.model_dump(mode="json"))
            return response
        except AppError:
            raise
        except Exception as exc:
            failure = MessageResponse(
                session_id=session_id,
                client_message_id=request.client_message_id,
                message="I couldn't safely process that request. Please try again.",
                status="failed",
                trace_id=trace_id,
            )
            await self._repository.fail_message(record, failure.model_dump(mode="json"))
            raise AppError(error_codes.MODEL_UNAVAILABLE, failure.message, 503, True) from exc

    async def stream(self, session_id: UUID, request: MessageRequest) -> AsyncGenerator[StreamEvent]:
        """Stream safe progress and the canonical idempotent turn response."""

        yield StreamEvent(event="status", data={"phase": "accepted", "message": "Message received"})
        yield StreamEvent(event="status", data={"phase": "thinking", "message": "Understanding your request"})
        try:
            response = await self.send(session_id, request)
        except AppError as exc:
            yield StreamEvent(
                event="error",
                data={
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "trace_id": str(uuid4()),
                        "retryable": exc.retryable,
                    }
                },
            )
            return
        yield StreamEvent(event="status", data={"phase": "composing", "message": "Preparing the response"})
        words = response.message.split(" ")
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            yield StreamEvent(event="delta", data={"text": f"{word}{suffix}"})
        yield StreamEvent(event="complete", data=response.model_dump(mode="json"))

    async def _customer_context(self, session: SessionRecord) -> str:
        customer = await self._restaurant_client.get_customer(session.customer_id)
        return json.dumps(
            {
                "customer_id": customer.id,
                "name": customer.name,
                "preferences": customer.preferences,
                "restaurant_timezone": "configured by the server",
            },
            separators=(",", ":"),
        )
