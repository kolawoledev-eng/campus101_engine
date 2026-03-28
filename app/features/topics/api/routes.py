from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.features.topics.repository import TopicsRepository
from app.features.topics.schemas import TopicIngestionRequest
from app.features.topics.service import TopicIngestionService

router = APIRouter(prefix="/api", tags=["topics"])


@router.get("/exams")
async def get_exams() -> List[Dict[str, Any]]:
    try:
        return TopicsRepository().list_exams()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/exams/{exam}/subjects")
async def get_subjects(exam: str) -> List[Dict[str, Any]]:
    try:
        return TopicsRepository().list_subjects(exam)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/exams/{exam}/{year}/{subject}/topics")
async def get_topics(exam: str, year: int, subject: str) -> List[Dict[str, Any]]:
    try:
        return TopicsRepository().list_topics(exam, year, subject)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/topics/ingest")
async def ingest_topics(payload: TopicIngestionRequest) -> Dict[str, Any]:
    try:
        if not payload.raw_topics and not payload.source_text:
            raise HTTPException(status_code=400, detail="Provide at least one of raw_topics or source_text")
        result = TopicIngestionService().ingest_topics(
            exam=payload.exam,
            year=payload.year,
            subject=payload.subject,
            raw_topics=payload.raw_topics,
            source_text=payload.source_text,
            source_url=payload.source_url,
            create_subject_if_missing=payload.create_subject_if_missing,
        )
        return {
            "status": "success",
            "exam": result.exam,
            "year": result.year,
            "subject": result.subject,
            "subject_created": result.subject_created,
            "normalized_topics": result.normalized_topics,
            "inserted_count": result.inserted_count,
            "skipped_count": result.skipped_count,
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

