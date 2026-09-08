"""FastAPI dependency-injection configuration."""

from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
from fastapi import Depends, Request
from langchain_groq import ChatGroq
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent import AgentGraphRunner
from src.client import RestaurantApiClient
from src.repositories import SessionRepository
from src.services.conversation_service import ConversationService, RunnerFactory
from src.services.session_service import SessionService
from src.settings import Settings, get_settings
from src.tools import build_restaurant_tools


def get_restaurant_client(request: Request) -> RestaurantApiClient:
    return RestaurantApiClient(cast(httpx.AsyncClient, request.app.state.restaurant_http_client))


async def get_database_session(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.database_session_factory
    async with factory() as database_session:
        yield database_session


def get_session_repository(database_session: AsyncSession = Depends(get_database_session)) -> SessionRepository:
    return SessionRepository(database_session)


def get_session_service(
    repository: SessionRepository = Depends(get_session_repository),
    restaurant_client: RestaurantApiClient = Depends(get_restaurant_client),
) -> SessionService:
    return SessionService(repository, restaurant_client)


def get_runner_factory(request: Request, settings: Settings = Depends(get_settings)) -> RunnerFactory:
    model = cast(ChatGroq, request.app.state.chat_model)
    checkpointer = cast(BaseCheckpointSaver[Any], request.app.state.checkpointer)

    def factory(restaurant_client: RestaurantApiClient, customer_id: int) -> AgentGraphRunner:
        tools = build_restaurant_tools(restaurant_client, customer_id)
        return AgentGraphRunner(
            model,
            tools,
            checkpointer,
            settings.max_graph_steps,
            settings.max_tool_calls,
            settings.max_mutations,
        )

    return factory


def get_conversation_service(
    repository: SessionRepository = Depends(get_session_repository),
    session_service: SessionService = Depends(get_session_service),
    restaurant_client: RestaurantApiClient = Depends(get_restaurant_client),
    runner_factory: RunnerFactory = Depends(get_runner_factory),
) -> ConversationService:
    return ConversationService(repository, session_service, restaurant_client, runner_factory)
