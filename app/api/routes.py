from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.db import get_supabase_client
from app.schemas import GenerateRequest, StudyNotesGenerateRequest, TopicIngestionRequest
from app.services.question_generator import QuestionGeneratorSupabase
from app.services.study_notes import StudyNotesService
from app.services.topic_ingestion import TopicIngestionService

router = APIRouter()


@router.get("/")
async def root() -> Dict[str, str]:
    return {
        "name": "grade99",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/api/exams")
async def get_exams() -> List[Dict[str, Any]]:
    try:
        supabase = get_supabase_client()
        return supabase.table("exams").select("*").order("name").execute().data
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/exams/{exam}/subjects")
async def get_subjects(exam: str) -> List[Dict[str, Any]]:
    try:
        supabase = get_supabase_client()
        exam_res = supabase.table("exams").select("id").eq("name", exam.upper()).limit(1).execute()
        if not exam_res.data:
            raise HTTPException(status_code=404, detail=f"Exam '{exam}' not found")
        exam_id = exam_res.data[0]["id"]
        return (
            supabase.table("subjects")
            .select("id,name")
            .eq("exam_id", exam_id)
            .order("name")
            .execute()
            .data
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/exams/{exam}/{year}/{subject}/topics")
async def get_topics(exam: str, year: int, subject: str) -> List[Dict[str, Any]]:
    try:
        supabase = get_supabase_client()
        exam_res = supabase.table("exams").select("id").eq("name", exam.upper()).limit(1).execute()
        if not exam_res.data:
            raise HTTPException(status_code=404, detail=f"Exam '{exam}' not found")
        exam_id = exam_res.data[0]["id"]

        subj_res = (
            supabase.table("subjects")
            .select("id")
            .eq("exam_id", exam_id)
            .eq("name", subject)
            .limit(1)
            .execute()
        )
        if not subj_res.data:
            raise HTTPException(status_code=404, detail=f"Subject '{subject}' not found under '{exam}'")
        subject_id = subj_res.data[0]["id"]

        topics = (
            supabase.table("syllabus_topics")
            .select("id,topic_name,year")
            .eq("subject_id", subject_id)
            .eq("year", year)
            .order("topic_name")
            .execute()
            .data
        )
        return [{"id": 0, "topic_name": "All Topics", "year": year}] + topics
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/generate")
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


@router.post("/api/topics/ingest")
async def ingest_topics(payload: TopicIngestionRequest) -> Dict[str, Any]:
    """
    Ingest syllabus topics with Claude normalization and Supabase upsert.
    """
    try:
        if not payload.raw_topics and not payload.source_text:
            raise HTTPException(
                status_code=400,
                detail="Provide at least one of raw_topics or source_text",
            )
        service = TopicIngestionService()
        result = service.ingest_topics(
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


@router.get("/api/questions")
async def get_questions(
    exam: str = Query(...),
    year: int = Query(...),
    subject: str = Query(...),
    difficulty: Optional[str] = Query(default=None),
    topic: Optional[str] = Query(default=None),
    limit: int = Query(default=40, ge=1, le=200),
) -> Dict[str, Any]:
    try:
        supabase = get_supabase_client()
        query = (
            supabase.table("generated_questions")
            .select("*")
            .eq("exam", exam.upper())
            .eq("year", year)
            .eq("subject", subject)
        )
        if difficulty:
            query = query.eq("difficulty", difficulty)
        if topic and topic.lower() != "all topics":
            query = query.eq("topic", topic)
        data = query.order("generated_at", desc=True).limit(limit).execute().data
        return {"status": "success", "count": len(data), "questions": data}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/study-notes/generate")
async def generate_study_notes(payload: StudyNotesGenerateRequest) -> Dict[str, Any]:
    try:
        service = StudyNotesService()
        result = service.generate_and_save(
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


@router.get("/api/study-notes")
async def get_study_notes(
    exam: str = Query(...),
    year: int = Query(...),
    subject: str = Query(...),
    topic: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    try:
        supabase = get_supabase_client()
        query = (
            supabase.table("study_notes")
            .select("*")
            .eq("exam", exam.upper())
            .eq("year", year)
            .eq("subject", subject)
        )
        if topic:
            query = query.eq("topic", topic)
        rows = query.order("sequence_number").limit(limit).execute().data
        return {"status": "success", "count": len(rows), "notes": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/study-note-sets/{note_set_id}")
async def get_study_note_set(note_set_id: str) -> Dict[str, Any]:
    try:
        supabase = get_supabase_client()
        set_res = supabase.table("study_note_sets").select("*").eq("id", note_set_id).limit(1).execute()
        if not set_res.data:
            raise HTTPException(status_code=404, detail="Study note set not found")
        note_set = set_res.data[0]
        notes = (
            supabase.table("study_notes")
            .select("*")
            .eq("note_set_id", note_set_id)
            .order("sequence_number")
            .execute()
            .data
        )
        return {"status": "success", "note_set": note_set, "count": len(notes), "notes": notes}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/question-sets/{set_id}")
async def get_question_set(set_id: str) -> Dict[str, Any]:
    try:
        supabase = get_supabase_client()
        set_res = supabase.table("question_sets").select("*").eq("id", set_id).limit(1).execute()
        if not set_res.data:
            raise HTTPException(status_code=404, detail="Question set not found")

        question_set = set_res.data[0]
        links = (
            supabase.table("question_set_items")
            .select("question_id,sequence_number")
            .eq("question_set_id", set_id)
            .order("sequence_number")
            .execute()
            .data
        )
        ids = [x["question_id"] for x in links]
        if not ids:
            return {"status": "success", "set": question_set, "count": 0, "questions": []}

        rows = supabase.table("generated_questions").select("*").in_("id", ids).execute().data
        by_id = {row["id"]: row for row in rows}
        ordered = [by_id[qid] for qid in ids if qid in by_id]
        return {"status": "success", "set": question_set, "count": len(ordered), "questions": ordered}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/user/{email}/history")
async def get_user_history(email: str, limit: int = Query(default=10, ge=1, le=200)) -> Dict[str, Any]:
    try:
        supabase = get_supabase_client()
        history = (
            supabase.table("generation_history")
            .select("*")
            .eq("generated_by", email)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
            .data
        )
        return {"status": "success", "email": email, "count": len(history), "history": history}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/user/{email}/stats")
async def get_user_stats(email: str) -> Dict[str, Any]:
    try:
        supabase = get_supabase_client()
        user_res = supabase.table("users").select("*").eq("email", email).limit(1).execute()
        if not user_res.data:
            raise HTTPException(status_code=404, detail="User not found")
        user = user_res.data[0]
        total_generations = (
            supabase.table("generation_history").select("*", count="exact").eq("generated_by", email).execute().count
            or 0
        )
        return {"status": "success", "email": email, "user": user, "total_generations": total_generations}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/admin/stats")
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

