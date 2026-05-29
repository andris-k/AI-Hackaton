from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from pathlib import Path

from app.routers.auth import router as auth_router
from app.routers.categories import router as categories_router
from app.routers.fixed_assets import router as fixed_assets_router
from app.routers.inventory_sessions import router as inventory_sessions_router
from app.services import auth_service

app = FastAPI(title="AI Hackaton")
_UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
def startup() -> None:
    auth_service.initialize_defaults()


app.include_router(auth_router)
app.include_router(fixed_assets_router)
app.include_router(categories_router)
app.include_router(inventory_sessions_router)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")
