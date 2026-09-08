"""Standard public error response models."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    trace_id: UUID
    retryable: bool = False


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: ErrorDetail
