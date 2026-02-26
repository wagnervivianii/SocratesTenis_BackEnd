from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.health import router as health_router
from app.routes.shorts import router as shorts_router

api_router = APIRouter()

# Health
api_router.include_router(health_router, tags=["health"])

# Auth (JWT)
api_router.include_router(auth_router, tags=["auth"])

# Shorts (YouTube)
api_router.include_router(shorts_router, tags=["shorts"])
