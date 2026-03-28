from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.db import get_supabase_client


class QuestionsRepository:
    def list_questions(
        self,
        exam: str,
        year: int,
        subject: str,
        difficulty: Optional[str] = None,
        topic: Optional[str] = None,
        limit: int = 40,
    ) -> list[Dict[str, Any]]:
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
        return query.order("generated_at", desc=True).limit(limit).execute().data

    def get_question_set(self, set_id: str) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
        supabase = get_supabase_client()
        set_res = supabase.table("question_sets").select("*").eq("id", set_id).limit(1).execute()
        if not set_res.data:
            raise ValueError("Question set not found")
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
            return question_set, []
        rows = supabase.table("generated_questions").select("*").in_("id", ids).execute().data
        by_id = {row["id"]: row for row in rows}
        ordered = [by_id[qid] for qid in ids if qid in by_id]
        return question_set, ordered

