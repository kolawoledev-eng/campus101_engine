from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.features.questions.repository import QuestionsRepository
from app.features.questions.schemas import GenerateRequest
from app.features.questions.service import QuestionGeneratorSupabase

router = APIRouter(prefix="/api", tags=["questions"])


@router.post("/generate")
async def generate_questions(payload: GenerateRequest) -> Dict[str, Any]:
    try:
        generator = QuestionGeneratorSupabase()
        questions = generator.generate_and_save(
            exam=payload.exam,
            year=payload.year,
            subject=payload.subject,
            difficulty=payload.difficulty,
            topic=payload.topic,
            count=payload.count,
            user_email=payload.user_email,
        )
        if not questions:
            raise HTTPException(status_code=500, detail="No questions generated")
        return {
            "status": "success",
            "count": len(questions),
            "saved_to_supabase": True,
            "questions": questions,
            "usage": {
                "input_tokens": generator.usage.input_tokens,
                "output_tokens": generator.usage.output_tokens,
                "total_cost": float(generator.usage.total_cost),
            },
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/questions")
async def get_questions(
    exam: str = Query(...),
    year: int = Query(...),
    subject: str = Query(...),
    difficulty: Optional[str] = Query(default=None),
    topic: Optional[str] = Query(default=None),
    limit: int = Query(default=40, ge=1, le=200),
) -> Dict[str, Any]:
    try:
        repo = QuestionsRepository()
        rows = repo.list_questions(exam, year, subject, difficulty, topic, limit)
        return {"status": "success", "count": len(rows), "questions": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/question-sets/{set_id}")
async def get_question_set(set_id: str) -> Dict[str, Any]:
    try:
        repo = QuestionsRepository()
        question_set, questions = repo.get_question_set(set_id)
        return {"status": "success", "set": question_set, "count": len(questions), "questions": questions}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

