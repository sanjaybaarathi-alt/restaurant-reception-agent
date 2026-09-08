"""Agent-owned session and idempotency tables."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.repositories.schema.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class SessionRecord(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    messages: Mapped[list["IdempotencyRecord"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class IdempotencyRecord(Base):
    __tablename__ = "agent_message_idempotency"
    __table_args__ = (UniqueConstraint("session_id", "client_message_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("agent_sessions.id", ondelete="CASCADE"), index=True)
    client_message_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    response: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    session: Mapped[SessionRecord] = relationship(back_populates="messages")
