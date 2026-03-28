from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings, validate_settings

settings = get_settings()
validate_settings(settings)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    openapi_version="3.1.0",
    description="Tree-based exam question generation with Supabase persistence.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

