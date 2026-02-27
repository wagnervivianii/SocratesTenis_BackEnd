from fastapi import APIRouter

from app.api.v1.endpoints.agenda import router as agenda_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.disponibilidade import router as disponibilidade_router
from app.api.v1.endpoints.events import router as events_router
from app.api.v1.endpoints.health import router as health_router
from app.routes.shorts import router as shorts_router

api_router = APIRouter()

# Health
api_router.include_router(health_router, tags=["health"])

# Auth (JWT) -> /api/v1/auth/...
api_router.include_router(auth_router, tags=["auth"])

# Agenda -> /api/v1/agenda/...
api_router.include_router(agenda_router, prefix="/agenda", tags=["agenda"])

# Disponibilidade -> /api/v1/disponibilidade/...
api_router.include_router(
    disponibilidade_router, prefix="/disponibilidade", tags=["disponibilidade"]
)

# Events -> /api/v1/events/...
api_router.include_router(events_router, prefix="/events", tags=["events"])

# Shorts (YouTube) -> /api/v1/shorts/...
api_router.include_router(shorts_router, tags=["shorts"])
