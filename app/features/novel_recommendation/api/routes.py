from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.features.novel_recommendation.schemas import NovelRecommendationRequest
from app.features.novel_recommendation.service import recommend_novels

router = APIRouter(prefix="/api", tags=["novel-recommendation"])


@router.post("/novels/recommend")
async def recommend(payload: NovelRecommendationRequest) -> Dict[str, Any]:
    try:
        return {
            "status": "success",
            "exam": payload.exam.upper(),
            "subject": payload.subject,
            "recommendations": recommend_novels(payload.exam, payload.subject, payload.count),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

