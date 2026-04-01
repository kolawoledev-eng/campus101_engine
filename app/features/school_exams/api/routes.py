from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.features.school_exams.repository import SchoolExamsRepository
from app.features.school_exams.schemas import SchoolQuestionGenerateRequest
from app.features.school_exams.service import SchoolQuestionService

router = APIRouter(prefix="/api/school-exams", tags=["school-exams"])


def _difficulty_split(total: int) -> list[tuple[str, int]]:
    base = total // 3
    rem = total % 3
    buckets = [("easy", base), ("medium", base), ("hard", base)]
    for i in range(rem):
        d, c = buckets[i]
        buckets[i] = (d, c + 1)
    return [(d, c) for d, c in buckets if c > 0]


@router.get("/institutions")
async def get_institutions(exam_mode: str = Query(...), year: int = Query(...)) -> Dict[str, Any]:
    try:
        rows = SchoolExamsRepository().list_institutions(exam_mode, year)
        return {"status": "success", "count": len(rows), "institutions": rows}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
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
        repo = SchoolExamsRepository()
        rows = repo.list_generated_questions(
            exam_mode=exam_mode,
            institution_name=institution_name,
            year=year,
            subject=subject,
            topic=topic,
            limit=limit,
        )
        note: str | None = None
        if not rows:
            # Auto top-up for empty buckets so users do not hit dead-ends.
            service = SchoolQuestionService()
            errors: list[str] = []
            topic_value = topic or "all topics"
            for diff, cnt in _difficulty_split(limit):
                try:
                    service.generate_and_save(
                        exam_mode=exam_mode,
                        institution_name=institution_name,
                        year=year,
                        subject=subject,
                        topic=topic_value,
                        difficulty=diff,
                        count=cnt,
                        user_email="api-auto",
                    )
                except Exception as exc:
                    errors.append(f"{diff}: {exc}")
            rows = repo.list_generated_questions(
                exam_mode=exam_mode,
                institution_name=institution_name,
                year=year,
                subject=subject,
                topic=topic,
                limit=limit,
            )
            if not rows:
                reason = "; ".join(errors) if errors else "unknown generation error"
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "No school questions available and auto-generation failed. "
                        f"Likely Claude/API quota or config issue: {reason}"
                    ),
                )
            if errors:
                note = f"partial generation notes: {'; '.join(errors)}"
        payload: Dict[str, Any] = {"status": "success", "count": len(rows), "questions": rows}
        if note:
            payload["auto_generation_note"] = note
        return payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

