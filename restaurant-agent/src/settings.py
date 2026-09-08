"""Typed application settings and centralized constants."""

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "Restaurant Reception Agent"
APP_VERSION = "0.1.0"
PROMPT_VERSION = "v1"
MAX_MESSAGE_LENGTH = 4_000
DEFAULT_MAX_GRAPH_STEPS = 8
DEFAULT_MAX_TOOL_CALLS = 12
DEFAULT_MAX_MUTATIONS = 6


class Settings(BaseSettings):
    """Configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    groq_api_key: SecretStr
    agent_model: str = "openai/gpt-oss-20b"
    restaurant_api_base_url: str = "http://localhost:8000"
    agent_database_url: str = "sqlite+aiosqlite:///./data/agent.db"
    langgraph_database_path: str = "./data/agent.db"
    restaurant_timezone: str = "Asia/Kolkata"
    llm_temperature: float = 0.0
    llm_max_tokens: int = Field(default=1_000, ge=100, le=4_000)
    llm_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    llm_retry_cap: int = Field(default=2, ge=0, le=3)
    upstream_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    max_graph_steps: int = Field(default=DEFAULT_MAX_GRAPH_STEPS, ge=2, le=20)
    max_tool_calls: int = Field(default=DEFAULT_MAX_TOOL_CALLS, ge=1, le=30)
    max_mutations: int = Field(default=DEFAULT_MAX_MUTATIONS, ge=1, le=10)
    session_retention_days: int = Field(default=30, ge=1, le=90)
    log_level: str = "INFO"

    @field_validator("restaurant_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("restaurant_api_base_url")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("restaurant_api_base_url must use http or https")
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings instance."""

    return Settings()
