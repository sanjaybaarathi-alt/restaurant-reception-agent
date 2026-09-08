"""Conversation session routes."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import suppress
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import StreamingResponse

from src.models.api import MessageRequest, MessageResponse, SessionResponse, StartSessionRequest, StreamEvent
from src.services import ConversationService, SessionService
from src.services.dependencies import get_conversation_service, get_session_service

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    request: StartSessionRequest,
    service: SessionService = Depends(get_session_service),
) -> SessionResponse:
    return await service.start(request)


@router.post("/{session_id}/messages", response_model=MessageResponse)
async def send_message(
    session_id: UUID,
    request: MessageRequest,
    service: ConversationService = Depends(get_conversation_service),
) -> MessageResponse:
    return await service.send(session_id, request)


def _encode_sse(event: StreamEvent) -> str:
    data = json.dumps(event.data, separators=(",", ":"), ensure_ascii=False)
    return f"event: {event.event}\ndata: {data}\n\n"


async def _event_stream(
    source: AsyncGenerator[StreamEvent], request: Request, heartbeat_seconds: float = 10.0
) -> AsyncIterator[str]:
    pending: asyncio.Task[StreamEvent] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(source))
            done, _ = await asyncio.wait({pending}, timeout=heartbeat_seconds)
            if await request.is_disconnected():
                return
            if not done:
                yield ": heartbeat\n\n"
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                return
            pending = None
            yield _encode_sse(event)
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with suppress(asyncio.CancelledError):
                await pending
        await source.aclose()


@router.post("/{session_id}/messages/stream", response_class=StreamingResponse)
async def stream_message(
    session_id: UUID,
    payload: MessageRequest,
    request: Request,
    service: ConversationService = Depends(get_conversation_service),
) -> StreamingResponse:
    """Stream one turn as safe SSE status, text delta, and completion events."""

    return StreamingResponse(
        _event_stream(service.stream(session_id, payload), request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
