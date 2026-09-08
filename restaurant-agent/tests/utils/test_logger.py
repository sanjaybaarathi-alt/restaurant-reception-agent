"""Tests for privacy-safe structured logging."""

import json
import logging

from src.utils.logger import JsonFormatter, log_event


def test_json_formatter_emits_structured_redacted_event() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "turn_completed", (), None)
    record.event_fields = {"event": "turn_completed", "email": "priya@example.com"}

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "turn_completed"
    assert payload["email"] == "[EMAIL]"
    assert payload["level"] == "INFO"


def test_log_event_attaches_fields() -> None:
    logger = logging.getLogger("test.structured")
    captured: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = Capture()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    secret_value = "".join(["sec", "ret"])
    try:
        log_event(logger, "tool_failed", token=secret_value)
    finally:
        logger.removeHandler(handler)

    assert captured[0].event_fields == {"event": "tool_failed", "token": "[REDACTED]"}
