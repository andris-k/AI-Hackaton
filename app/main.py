from fastapi import FastAPI

from app.routers.auth import router as auth_router
from app.routers.categories import router as categories_router
from app.routers.fixed_assets import router as fixed_assets_router
from app.services import auth_service

app = FastAPI(title="AI Hackaton")


@app.on_event("startup")
def startup() -> None:
    auth_service.initialize_defaults()


app.include_router(auth_router)
app.include_router(fixed_assets_router)
app.include_router(categories_router)
