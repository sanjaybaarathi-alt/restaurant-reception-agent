"""Deterministic customer identity and session creation service."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from src.client import RestaurantApiClient
from src.models.api import SessionCustomer, SessionResponse, StartSessionRequest
from src.repositories import SessionRepository
from src.repositories.schema import SessionRecord
from src.utils.exceptions import AppError, error_codes


class SessionService:
    def __init__(self, repository: SessionRepository, restaurant_client: RestaurantApiClient) -> None:
        self._repository = repository
        self._restaurant_client = restaurant_client

    async def start(self, request: StartSessionRequest) -> SessionResponse:
        identity = request.customer
        by_phone = await self._restaurant_client.lookup_customer(phone=identity.phone) if identity.phone else None
        by_email = await self._restaurant_client.lookup_customer(email=str(identity.email)) if identity.email else None
        if by_phone and by_email and by_phone.id != by_email.id:
            raise AppError(
                error_codes.IDENTITY_CONFLICT,
                "The supplied phone and email belong to different customer records.",
                409,
            )
        customer = by_phone or by_email
        is_new = customer is None
        if customer is None:
            if not identity.name:
                raise AppError(
                    error_codes.CUSTOMER_NOT_FOUND,
                    "No customer was found. Please provide a name to create one.",
                    422,
                )
            customer = await self._restaurant_client.create_customer(
                name=identity.name,
                phone=identity.phone,
                email=str(identity.email) if identity.email else None,
            )
        session_id = uuid4()
        created_at = datetime.now(UTC)
        await self._repository.create(
            SessionRecord(id=session_id, customer_id=customer.id, customer_name=customer.name, created_at=created_at)
        )
        return SessionResponse(
            session_id=session_id,
            customer=SessionCustomer(id=customer.id, name=customer.name, is_new=is_new),
            created_at=created_at,
        )

    async def require_session(self, session_id: UUID) -> SessionRecord:
        session = await self._repository.get(session_id)
        if session is None:
            raise AppError(error_codes.SESSION_NOT_FOUND, "Conversation session not found.", 404)
        return session
