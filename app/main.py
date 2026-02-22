from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router

# Carrega variáveis do .env no root do projeto (se existir),
# sem sobrescrever variáveis já definidas no ambiente.
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

# Importa settings somente após carregar o .env
from app.core.config import settings  # noqa: E402

app = FastAPI(title=settings.app_name, version=settings.version)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": f"{settings.app_name} online",
        "env": settings.env,
        "cors_origins": origins,
        "health": "/api/v1/health",
        "shorts": "/api/v1/shorts",
        "docs": "/docs",
        "redoc": "/redoc",
    }


# ✅ Tudo que é v1 fica centralizado no api_router
app.include_router(api_router, prefix="/api/v1")
