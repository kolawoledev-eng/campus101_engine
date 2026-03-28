from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.features.study_notes.repository import StudyNotesRepository
from app.features.study_notes.schemas import StudyNotesGenerateRequest
from app.features.study_notes.service import StudyNotesService

router = APIRouter(prefix="/api", tags=["study-notes"])


@router.post("/study-notes/generate")
async def generate_study_notes(payload: StudyNotesGenerateRequest) -> Dict[str, Any]:
    try:
        result = StudyNotesService().generate_and_save(
            exam=payload.exam,
            year=payload.year,
            subject=payload.subject,
            topic=payload.topic,
            min_subtopics=payload.min_subtopics,
            read_time_target_minutes=payload.read_time_target_minutes,
            user_email=payload.user_email,
            source_url=payload.source_url,
        )
        return {
            "status": "success",
            "note_set_id": result.note_set_id,
            "exam": result.exam,
            "year": result.year,
            "subject": result.subject,
            "topic": result.topic,
            "total_subtopics": result.total_subtopics,
            "notes": result.notes,
            "usage": {
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_cost": result.total_cost,
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/study-notes")
async def get_study_notes(
    exam: str = Query(...),
    year: int = Query(...),
    subject: str = Query(...),
    topic: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    try:
        rows = StudyNotesRepository().list_notes(exam, year, subject, topic, limit)
        return {"status": "success", "count": len(rows), "notes": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/study-note-sets/{note_set_id}")
async def get_study_note_set(note_set_id: str) -> Dict[str, Any]:
    try:
        note_set, notes = StudyNotesRepository().get_note_set(note_set_id)
        return {"status": "success", "note_set": note_set, "count": len(notes), "notes": notes}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

