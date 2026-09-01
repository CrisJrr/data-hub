"""
Structured logging configuration for Data Hub.

Provides:
  - JSON formatter for production (machine-parseable)
  - Human-readable formatter for development
  - Correlation ID support via contextvars
  - Request logging middleware
"""
import logging
import json
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Correlation ID — propagated across async boundaries
# ---------------------------------------------------------------------------
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")


def get_correlation_id() -> str:
    return correlation_id_var.get()


def set_correlation_id(cid: str | None = None) -> str:
    cid = cid or uuid.uuid4().hex[:12]
    correlation_id_var.set(cid)
    return cid


# ---------------------------------------------------------------------------
# JSON Formatter
# ---------------------------------------------------------------------------
class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        # Add extra fields if present
        if hasattr(record, "extra_data") and record.extra_data:
            log_entry["data"] = record.extra_data

        # Add exception info
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        # Add source location for debug
        if record.levelno == logging.DEBUG:
            log_entry["source"] = {
                "file": record.pathname,
                "line": record.lineno,
                "func": record.funcName,
            }

        return json.dumps(log_entry, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Human-readable Formatter (dev)
# ---------------------------------------------------------------------------
class DevFormatter(logging.Formatter):
    """Colored, human-readable format for terminal."""

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[1;31m",  # Bold Red
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        cid = get_correlation_id()
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]

        msg = f"{color}{ts} [{record.levelname:8s}]{self.RESET} {record.name}: {record.getMessage()}"

        if cid != "-":
            msg = f"\033[90m[{cid}]\033[0m {msg}"

        if record.exc_info and record.exc_info[0]:
            msg += f"\n{self.formatException(record.exc_info)}"

        return msg


# ---------------------------------------------------------------------------
# Setup function
# ---------------------------------------------------------------------------
def setup_logging(environment: str = "production") -> None:
    """Configure root logger with structured JSON or dev formatter."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Remove existing handlers
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if environment == "development":
        handler.setFormatter(DevFormatter())
        handler.setLevel(logging.DEBUG)
    else:
        handler.setFormatter(JSONFormatter())
        handler.setLevel(logging.INFO)

    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)
