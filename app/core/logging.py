from datetime import UTC, datetime
import json
import logging
import sys
from typing import Any

from app.core.context import get_correlation_id, get_dealership_id_ctx

# Explicitly prohibited PII keys (GDPR guardrail — System Design Section 7.1)
FORBIDDEN_PII_FIELDS: frozenset[str] = frozenset(
    {
        "email",
        "phone",
        "first_name",
        "last_name",
        "notes",
        "enquiry_notes",
        "summary",
        "customer_name",
    }
)

# Standard LogRecord attributes that should not be copied into custom fields
_STANDARD_LOG_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
)


def _sanitize_value(value: Any) -> Any:
    """Recursively strip any forbidden PII keys from nested structures."""
    if isinstance(value, dict):
        return {
            k: _sanitize_value(v)
            for k, v in value.items()
            if str(k).lower() not in FORBIDDEN_PII_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    """Emits single-line structured JSON logs without customer PII."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event", record.getMessage()),
            "correlation_id": getattr(record, "correlation_id", None)
            or get_correlation_id(),
            "dealership_id": getattr(record, "dealership_id", None)
            or get_dealership_id_ctx(),
        }

        # Include safe extra fields while strictly scrubbing PII keys
        for key, value in record.__dict__.items():
            if key in _STANDARD_LOG_ATTRS or key in payload or key.startswith("_"):
                continue
            if key.lower() in FORBIDDEN_PII_FIELDS:
                continue
            payload[key] = _sanitize_value(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(log_level: str = "INFO") -> None:
    """Configure root and application loggers to emit structured JSON to stdout."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Silence noisy default uvicorn access logs (replaced by our structured middleware)
    logging.getLogger("uvicorn.access").disabled = True
