from fastapi import APIRouter

##from app.api.v1.health import router as health_router
from app.routes.shorts import router as shorts_router  # <-- ADICIONA

api_router = APIRouter(prefix="/api/v1")

##api_router.include_router(health_router)
api_router.include_router(shorts_router)  # <-- ADICIONA
