"""Public API request and response models."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerIdentity(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, min_length=3, max_length=32)
    email: EmailStr | None = None

    @model_validator(mode="after")
    def require_identifier(self) -> "CustomerIdentity":
        if not self.phone and not self.email:
            raise ValueError("phone or email is required")
        return self


class StartSessionRequest(StrictModel):
    customer: CustomerIdentity


class SessionCustomer(StrictModel):
    id: int
    name: str
    is_new: bool


class SessionResponse(StrictModel):
    session_id: UUID
    customer: SessionCustomer
    created_at: datetime


class MessageRequest(StrictModel):
    client_message_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4_000)
    verbose: bool = False


class ToolAuditEvent(StrictModel):
    sequence: int = Field(ge=1)
    event_type: Literal["decision", "tool_call", "tool_result"]
    summary: str | None = None
    tool_name: str | None = None
    status: Literal["planned", "succeeded", "failed", "skipped"]
    duration_ms: int | None = Field(default=None, ge=0)


class Usage(StrictModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class MessageResponse(StrictModel):
    session_id: UUID
    client_message_id: str
    message: str
    status: Literal["completed", "needs_input", "failed"]
    trace_id: UUID
    audit_events: list[ToolAuditEvent] = Field(default_factory=list)
    usage: Usage | None = None


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(StrictModel):
    status: Literal["ready", "not_ready"]


class StreamEvent(StrictModel):
    """One privacy-safe event emitted by the conversation stream."""

    event: Literal["status", "delta", "complete", "error"]
    data: dict[str, Any]
