from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings, validate_settings
from app.core.db import get_supabase_client
from app.features.novel_recommendation.api.routes import router as novels_router
from app.features.practice.api.routes import router as practice_router
from app.features.questions.api.routes import router as questions_router
from app.features.school_exams.api.routes import router as school_exams_router
from app.features.study_notes.api.routes import router as study_notes_router
from app.features.topics.api.routes import router as topics_router

settings = get_settings()
validate_settings(settings)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    openapi_version="3.1.0",
    description="Tree-based exam learning platform with questions and study notes.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> Dict[str, str]:
    return {"name": "grade99", "docs": "/docs", "health": "/health"}


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/user/{email}/history", tags=["users"])
async def get_user_history(email: str, limit: int = Query(default=10, ge=1, le=200)) -> Dict[str, Any]:
    try:
        rows = (
            get_supabase_client()
            .table("generation_history")
            .select("*")
            .eq("generated_by", email)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        return {"status": "success", "email": email, "count": len(rows), "history": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/user/{email}/stats", tags=["users"])
async def get_user_stats(email: str) -> Dict[str, Any]:
    try:
        supabase = get_supabase_client()
        user_res = supabase.table("users").select("*").eq("email", email).limit(1).execute()
        if not user_res.data:
            raise HTTPException(status_code=404, detail="User not found")
        total_generations = (
            supabase.table("generation_history").select("*", count="exact").eq("generated_by", email).execute().count
            or 0
        )
        return {"status": "success", "email": email, "user": user_res.data[0], "total_generations": total_generations}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/stats", tags=["admin"])
async def get_admin_stats() -> Dict[str, Any]:
    try:
        supabase = get_supabase_client()
        q_count = supabase.table("generated_questions").select("*", count="exact").execute().count or 0
        g_count = supabase.table("generation_history").select("*", count="exact").execute().count or 0
        u_count = supabase.table("users").select("*", count="exact").execute().count or 0
        costs = supabase.table("question_sets").select("total_cost").execute().data
        total_cost = sum(float(item.get("total_cost") or 0) for item in costs)
        return {
            "status": "success",
            "statistics": {
                "total_questions": q_count,
                "total_generation_requests": g_count,
                "total_users": u_count,
                "total_api_cost": total_cost,
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


app.include_router(topics_router)
app.include_router(questions_router)
app.include_router(study_notes_router)
app.include_router(novels_router)
app.include_router(practice_router)
app.include_router(school_exams_router)

