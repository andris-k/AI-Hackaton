from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.routers.auth import router as auth_router
from app.routers.categories import router as categories_router
from app.routers.fixed_assets import router as fixed_assets_router
from app.routers.inventory_sessions import router as inventory_sessions_router
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


@app.on_event("startup")
def startup() -> None:
    auth_service.initialize_defaults()


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
app.include_router(inventory_sessions_router)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")
