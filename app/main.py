import logging
import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.logging_config import configure_logging, mask_path, start_request_context

configure_logging()

from app.routers.audit import router as audit_router  # noqa: E402  (logging is configured first)
from app.routers.auth import router as auth_router  # noqa: E402
from app.routers.categories import router as categories_router
from app.routers.fixed_assets import router as fixed_assets_router
from app.routers.inventory_sessions import router as inventory_sessions_router
from app.routers.locations import router as locations_router
from app.repositories import audit_repository  # noqa: E402
from app.services import auth_service

_IS_PRODUCTION = config.is_production()

# The interactive API docs (/docs, /redoc, /openapi.json) are for development only.
app = FastAPI(
    title="AI Hackaton",
    docs_url=None if _IS_PRODUCTION else "/docs",
    redoc_url=None if _IS_PRODUCTION else "/redoc",
    openapi_url=None if _IS_PRODUCTION else "/openapi.json",
)
_UPLOADS_DIR = config.uploads_dir()
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
_STATIC_DIR = Path(__file__).resolve().parent / "static"


_logger = logging.getLogger("app")
_request_logger = logging.getLogger("app.request")
_error_logger = logging.getLogger("app.error")
_UNLOGGED_PREFIXES = ("/static/", "/uploads/", "/favicon.ico")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_ERROR_PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8" />
<title>Something went wrong</title><link rel="stylesheet" href="/static/app.css" /></head>
<body><main class="auth-main"><div class="auth-card"><h1>Something went wrong</h1>
<p class="subtitle">The error has been logged. Please try again, or go back to the <a href="/">start page</a>.</p>
<p class="mono">Reference: {request_id}</p></div></main></body></html>"""


@app.on_event("startup")
def startup() -> None:
    # Apply again here: if uvicorn configured its own logging after importing this
    # module (e.g. uvicorn.run(app)), this restores ours. The setup is idempotent.
    configure_logging()
    auth_service.initialize_defaults()
    retention_days = config.audit_retention_days()
    if retention_days:
        removed = audit_repository.delete_events_older_than(retention_days)
        if removed:
            _logger.info("Removed old audit events", extra={"removed": removed, "retention_days": retention_days})
    _logger.info(
        "Application started",
        extra={
            "mode": "production" if _IS_PRODUCTION else "development",
            "database": str(config.database_path()),
            "uploads": str(_UPLOADS_DIR),
            "password_reset": "on screen" if config.show_reset_link_on_screen()
            else ("email" if config.smtp_settings() else "off"),
        },
    )


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """Log one line per request, tag it with a request id and catch unhandled errors."""
    incoming_id = request.headers.get("x-request-id", "")
    request_id = incoming_id if _REQUEST_ID_PATTERN.match(incoming_id) else uuid.uuid4().hex[:12]
    context = start_request_context(request_id)
    path = request.url.path
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        _error_logger.exception(
            "Unhandled error", extra={"method": request.method, "path": mask_path(path)}
        )
        response = HTMLResponse(_ERROR_PAGE.format(request_id=request_id), status_code=500)

    response.headers["X-Request-ID"] = request_id
    if not path.startswith(_UNLOGGED_PREFIXES):
        status = response.status_code
        level = logging.ERROR if status >= 500 else logging.WARNING if status >= 400 else logging.INFO
        _request_logger.log(
            level,
            f"{request.method} {mask_path(path)} {status}",
            extra={
                "method": request.method,
                "path": mask_path(path),
                "status": status,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "user_id": context.get("user_id"),
            },
        )
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if _IS_PRODUCTION:
        # Tell browsers to use HTTPS only. Requires the site to be served over HTTPS.
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    # Browsers request /favicon.ico on their own; serve the SVG icon there too.
    return FileResponse(_STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


app.include_router(auth_router)
app.include_router(fixed_assets_router)
app.include_router(categories_router)
app.include_router(locations_router)
app.include_router(inventory_sessions_router)
app.include_router(audit_router)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")
