"""Privacy-conscious structured logging helpers."""

import json
import logging
import re
from typing import Any

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)\+?[\d][\d\s()-]{7,}[\d](?!\w)")
SECRET_KEYS = {"authorization", "api_key", "groq_api_key", "openai_api_key", "password", "token"}


class JsonFormatter(logging.Formatter):
    """Render standard log records as one-line JSON for log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        event_fields = getattr(record, "event_fields", None)
        if isinstance(event_fields, dict):
            payload.update(redact(event_fields))
        if record.exc_info:
            payload["exception_type"] = record.exc_info[0].__name__ if record.exc_info[0] else "Unknown"
        return json.dumps(redact(payload), default=str, separators=(",", ":"))


def redact(value: Any) -> Any:
    """Recursively redact common PII and secret values."""

    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in SECRET_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return PHONE_PATTERN.sub("[PHONE]", EMAIL_PATTERN.sub("[EMAIL]", value))
    return value


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    logger.info(event, extra={"event_fields": {"event": event, **redact(fields)}})
