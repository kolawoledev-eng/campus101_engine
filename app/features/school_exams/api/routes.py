from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.features.school_exams.repository import SchoolExamsRepository
from app.features.school_exams.schemas import SchoolQuestionGenerateRequest
from app.features.school_exams.service import SchoolQuestionService

router = APIRouter(prefix="/api/school-exams", tags=["school-exams"])


@router.get("/institutions")
async def get_institutions(exam_mode: str = Query(...), year: int = Query(...)) -> Dict[str, Any]:
    try:
        rows = SchoolExamsRepository().list_institutions(exam_mode, year)
        return {"status": "success", "count": len(rows), "institutions": rows}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/subjects")
async def get_subjects(
    exam_mode: str = Query(...),
    institution_name: str = Query(...),
    year: int = Query(...),
) -> Dict[str, Any]:
    try:
        rows = SchoolExamsRepository().list_subjects(exam_mode, institution_name, year)
        return {"status": "success", "count": len(rows), "subjects": rows}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/topics")
async def get_topics(
    exam_mode: str = Query(...),
    institution_name: str = Query(...),
    year: int = Query(...),
    subject: str = Query(...),
) -> Dict[str, Any]:
    try:
        rows = SchoolExamsRepository().list_topics(exam_mode, institution_name, year, subject)
        return {"status": "success", "count": len(rows), "topics": rows}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/generate")
async def generate_questions(payload: SchoolQuestionGenerateRequest) -> Dict[str, Any]:
    try:
        return SchoolQuestionService().generate_and_save(
            exam_mode=payload.exam_mode,
            institution_name=payload.institution_name,
            year=payload.year,
            subject=payload.subject,
            topic=payload.topic,
            difficulty=payload.difficulty,
            count=payload.count,
            user_email=payload.user_email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/questions")
async def get_questions(
    exam_mode: str = Query(...),
    institution_name: str = Query(...),
    year: int = Query(...),
    subject: str = Query(...),
    topic: Optional[str] = Query(default=None),
    limit: int = Query(default=40, ge=1, le=200),
) -> Dict[str, Any]:
    try:
        rows = SchoolExamsRepository().list_generated_questions(
            exam_mode=exam_mode,
            institution_name=institution_name,
            year=year,
            subject=subject,
            topic=topic,
            limit=limit,
        )
        return {"status": "success", "count": len(rows), "questions": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

