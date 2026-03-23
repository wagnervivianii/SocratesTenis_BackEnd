from fastapi import APIRouter

from app.api.v1.endpoints.agenda import router as agenda_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.bookable_slots import router as bookable_slots_router
from app.api.v1.endpoints.catalogs import router as catalogs_router
from app.api.v1.endpoints.class_groups import router as class_groups_router
from app.api.v1.endpoints.disponibilidade import router as disponibilidade_router
from app.api.v1.endpoints.events import router as events_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.students import router as students_router
from app.api.v1.endpoints.teachers import router as teachers_router
from app.api.v1.endpoints.trial_lessons import router as trial_lessons_router
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
    disponibilidade_router,
    prefix="/disponibilidade",
    tags=["disponibilidade"],
)

# Events -> /api/v1/events/...
api_router.include_router(events_router, prefix="/events", tags=["events"])

# Trial Lessons -> /api/v1/trial-lessons/...
api_router.include_router(trial_lessons_router, tags=["trial-lessons"])

# Bookable Slots -> /api/v1/bookable-slots/...
api_router.include_router(bookable_slots_router, tags=["bookable-slots"])

# Catalogs -> /api/v1/catalogs/...
api_router.include_router(catalogs_router, tags=["catalogs"])

# Class Groups -> /api/v1/class-groups/...
api_router.include_router(class_groups_router, tags=["class-groups"])

# Teachers -> /api/v1/teachers/...
api_router.include_router(teachers_router, tags=["teachers"])

# Students -> /api/v1/students/...
api_router.include_router(students_router, tags=["students"])

# Shorts (YouTube) -> /api/v1/shorts/...
api_router.include_router(shorts_router, tags=["shorts"])
