"""Repository for sessions and turn idempotency."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.schema import IdempotencyRecord, SessionRecord


class SessionRepository:
    def __init__(self, database_session: AsyncSession) -> None:
        self._database_session = database_session

    async def create(self, session: SessionRecord) -> SessionRecord:
        self._database_session.add(session)
        await self._database_session.commit()
        await self._database_session.refresh(session)
        return session

    async def get(self, session_id: UUID) -> SessionRecord | None:
        return await self._database_session.get(SessionRecord, session_id)

    async def get_message(self, session_id: UUID, client_message_id: str) -> IdempotencyRecord | None:
        result = await self._database_session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.session_id == session_id,
                IdempotencyRecord.client_message_id == client_message_id,
            )
        )
        return result.scalar_one_or_none()

    async def begin_message(self, session_id: UUID, client_message_id: str, request_hash: str) -> IdempotencyRecord:
        record = IdempotencyRecord(
            session_id=session_id,
            client_message_id=client_message_id,
            request_hash=request_hash,
            status="processing",
        )
        self._database_session.add(record)
        await self._database_session.commit()
        await self._database_session.refresh(record)
        return record

    async def complete_message(self, record: IdempotencyRecord, response: dict[str, object]) -> None:
        record.status = "completed"
        record.response = response
        await self._database_session.commit()

    async def fail_message(self, record: IdempotencyRecord, response: dict[str, object]) -> None:
        record.status = "failed"
        record.response = response
        await self._database_session.commit()
