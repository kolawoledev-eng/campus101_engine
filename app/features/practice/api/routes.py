from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.db import get_supabase_client

router = APIRouter(prefix="/api/practice", tags=["practice"])


@router.get("/session")
async def practice_session(
    exam: str = Query(...),
    year: int = Query(...),
    subject: str = Query(...),
    difficulty: str = Query(...),
    topic: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> Dict[str, Any]:
    """
    Build a practice set: prefer rows from past_questions, then generated_questions.
    """
    try:
        supabase = get_supabase_client()
        fields = (
            "id,question_text,option_a,option_b,option_c,option_d,correct_answer,explanation,topic"
        )
        past: List[Dict[str, Any]] = []
        try:
            q = (
                supabase.table("past_questions")
                .select(fields + ",source_label")
                .eq("exam", exam.upper())
                .eq("year", year)
                .eq("subject", subject)
                .eq("difficulty", difficulty)
            )
            if topic and topic.lower() != "all topics":
                q = q.eq("topic", topic)
            past = q.limit(limit).execute().data or []
        except Exception:
            past = []

        need = limit - len(past)
        gen: List[Dict[str, Any]] = []
        if need > 0:
            q2 = (
                supabase.table("generated_questions")
                .select(fields)
                .eq("exam", exam.upper())
                .eq("year", year)
                .eq("subject", subject)
                .eq("difficulty", difficulty)
            )
            if topic and topic.lower() != "all topics":
                q2 = q2.eq("topic", topic)
            gen = q2.limit(need).execute().data or []

        for p in past:
            p["source"] = "past"
        for g in gen:
            g["source"] = "generated"

        combined = past + gen
        random.shuffle(combined)
        return {
            "status": "success",
            "count": len(combined),
            "past_count": len(past),
            "generated_count": len(gen),
            "questions": combined[:limit],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
