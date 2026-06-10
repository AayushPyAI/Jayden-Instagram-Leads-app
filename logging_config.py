"""Application logging for CloudWatch (structured text, health-check noise reduced)."""

from __future__ import annotations

import contextvars
import logging
import os
import sys
from typing import Any

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("-")  # type: ignore[attr-defined]
        return True


class HealthCheckAccessFilter(logging.Filter):
    """Drop ALB health probe lines from uvicorn access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "GET /health" in msg or "HEAD /health" in msg:
            return False
        return True


def setup_logging() -> None:
    level_name = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] request_id=%(request_id)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())
    root.addHandler(handler)

    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).setLevel(level)

    access = logging.getLogger("uvicorn.access")
    access.setLevel(logging.WARNING if level > logging.DEBUG else logging.INFO)
    access.addFilter(HealthCheckAccessFilter())

    logging.getLogger("jayden").setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Child logger under the jayden.* namespace."""
    if not name.startswith("jayden."):
        name = f"jayden.{name}"
    return logging.getLogger(name)


def log_fields(**fields: Any) -> str:
    """Serialize key=value pairs for log message bodies."""
    parts: list[str] = []
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            inner = ", ".join(str(v) for v in value)
            parts.append(f"{key}=[{inner}]")
        elif isinstance(value, dict):
            inner = ", ".join(f"{k}={v}" for k, v in value.items())
            parts.append(f"{key}={{{inner}}}")
        else:
            text = str(value).replace("\n", " ").strip()
            if len(text) > 500:
                text = text[:497] + "..."
            parts.append(f"{key}={text}")
    return " ".join(parts)
