"""FastAPI application entry point."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from langchain_groq import ChatGroq  # noqa: E402
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from src.api import register_exception_handlers  # noqa: E402
from src.middleware.request_context import RequestContextMiddleware  # noqa: E402
from src.routes import health_router, sessions_router, ui_router  # noqa: E402
from src.routes.ui import FRONTEND_DIRECTORY  # noqa: E402
from src.settings import APP_NAME, APP_VERSION, get_settings  # noqa: E402
from src.utils.logger import configure_logging  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    Path(settings.langgraph_database_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(settings.agent_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with (
        httpx.AsyncClient(
            base_url=settings.restaurant_api_base_url,
            timeout=httpx.Timeout(settings.upstream_timeout_seconds),
        ) as restaurant_http_client,
        AsyncSqliteSaver.from_conn_string(settings.langgraph_database_path) as checkpointer,
    ):
        await checkpointer.setup()
        app.state.database_engine = engine
        app.state.database_session_factory = session_factory
        app.state.restaurant_http_client = restaurant_http_client
        app.state.checkpointer = checkpointer
        app.state.chat_model = ChatGroq(
            model_name=settings.agent_model,
            api_key=settings.groq_api_key,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_retry_cap,
        )
        yield
    await engine.dispose()


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
asset_directory = FRONTEND_DIRECTORY / "assets"
if asset_directory.exists():
    app.mount("/assets", StaticFiles(directory=asset_directory), name="assets")
else:
    app.mount("/static", StaticFiles(directory=FRONTEND_DIRECTORY), name="static")
app.include_router(ui_router)
app.include_router(health_router)
app.include_router(sessions_router)
register_exception_handlers(app)
