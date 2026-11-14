"""Application logging: one-time setup, per-request context and the audit log.

Settings (environment variables):
    LOG_LEVEL   DEBUG / INFO (default) / WARNING / ERROR
    LOG_FORMAT  "text" (default in development) or "json" (default in production)

Everything goes to stdout, which hosting platforms collect automatically.

Loggers:
    app.request  one line per HTTP request (method, path, status, duration, user)
    app.error    unhandled exceptions with traceback
    audit        who did what: logins, asset/category changes, inventory session lifecycle
    app.*        everything else (startup, email, ...)
"""

from __future__ import annotations

import contextvars
import json
import logging
import logging.config
import os
import re
from datetime import datetime, timezone
from typing import Any

from app import config

# Per-request context shared by the middleware, the auth layer and the log formatters.
# A mutable dict is used so values set inside sync route handlers (which run in a
# worker thread with a copied context) are still visible to the middleware.
_request_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "request_context", default=None
)

_SENSITIVE_PATHS = (re.compile(r"^(/reset-password/)[^/?#]+"),)
_AUDIT_LOGGER = logging.getLogger("audit")
_STANDARD_RECORD_ATTRS = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def start_request_context(request_id: str) -> dict[str, Any]:
    context: dict[str, Any] = {"request_id": request_id, "user_id": None, "user_email": None}
    _request_context.set(context)
    return context


def current_request_context() -> dict[str, Any]:
    return _request_context.get() or {}


def set_request_user(user_id: object, email: object) -> None:
    """Called by the auth layer once the signed-in user is known."""
    context = _request_context.get()
    if context is not None:
        context["user_id"] = user_id
        context["user_email"] = email


def mask_path(path: str) -> str:
    """Hide secrets that appear in URLs, e.g. password reset tokens."""
    for pattern in _SENSITIVE_PATHS:
        path = pattern.sub(r"\1***", path)
    return path


def audit(event: str, *, actor: str | None = None, **fields: Any) -> None:
    """Record a business event, e.g. audit("asset.updated", asset_id=..., changes={...}).

    The acting user defaults to the signed-in user of the current request.
    Never pass passwords, tokens or cookies.
    """
    context = current_request_context()
    _AUDIT_LOGGER.info(
        event,
        extra={"event": event, "actor": actor or context.get("user_email"), "fields": fields},
    )


def diff_fields(before: Any, after: Any, names: tuple[str, ...]) -> dict[str, list[Any]]:
    """{field: [old, new]} for the fields whose values differ between two rows/mappings."""
    changes: dict[str, list[Any]] = {}
    for name in names:
        old = before[name] if before is not None and name in before.keys() else None
        new = after[name] if after is not None and name in after.keys() else None
        if old != new:
            changes[name] = [old, new]
    return changes


class _ContextFilter(logging.Filter):
    """Adds request_id / user to every record so formatters can use them."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = current_request_context()
        record.request_id = context.get("request_id") or "-"
        record.user = context.get("user_email") or "-"
        return True


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _STANDARD_RECORD_ATTRS and key not in {"request_id", "user", "color_message"}
    }


class TextFormatter(logging.Formatter):
    """Readable single-line format for local development."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s", "%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        extras = _extra_fields(record)
        if record.name == "app.request":
            # Method, path and status are already in the message.
            extras = {"duration_ms": extras.get("duration_ms"), "user": getattr(record, "user", "-")}
        elif record.name == "audit":
            extras.pop("event", None)
            fields = extras.pop("fields", {}) or {}
            extras = {**extras, **fields}
        if extras:
            line += "  " + " ".join(f"{key}={_compact(value)}" for key, value in extras.items())
        return line


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for log services in production."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "user": getattr(record, "user", "-"),
        }
        payload.update(_extra_fields(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def _compact(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False) if " " in value or not value else value
    return json.dumps(value, default=str, ensure_ascii=False)


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    log_format = os.getenv("LOG_FORMAT", "").strip().lower() or ("json" if config.is_production() else "text")
    formatter = "json" if log_format == "json" else "text"

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"context": {"()": _ContextFilter}},
        "formatters": {
            "text": {"()": TextFormatter},
            "json": {"()": JsonFormatter},
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": formatter,
                "filters": ["context"],
            },
        },
        "root": {"level": level, "handlers": ["stdout"]},
        "loggers": {
            # Our request logger replaces uvicorn's access log (which would also leak reset tokens).
            "uvicorn.access": {"handlers": [], "propagate": False, "level": "CRITICAL"},
            "uvicorn": {"handlers": [], "propagate": True},
            "uvicorn.error": {"handlers": [], "propagate": True},
            # Third-party noise.
            "fontTools": {"level": "WARNING"},
            "fpdf": {"level": "WARNING"},
        },
    })
