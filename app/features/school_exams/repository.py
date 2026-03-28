from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.db import get_supabase_client


class SchoolExamsRepository:
    VALID_MODES = {"post-utme", "jupeb"}

    def list_institutions(self, exam_mode: str, year: int) -> List[Dict[str, Any]]:
        if exam_mode not in self.VALID_MODES:
            raise ValueError("exam_mode must be 'post-utme' or 'jupeb'")
        supabase = get_supabase_client()
        rows = (
            supabase.table("institution_exam_offerings")
            .select("institution_id, institutions(name, short_code)")
            .eq("exam_mode", exam_mode)
            .eq("year", year)
            .eq("active", True)
            .execute()
            .data
        )
        return [
            {"institution_name": row["institutions"]["name"], "short_code": row["institutions"].get("short_code")}
            for row in rows
        ]

    def _get_offering_id(self, exam_mode: str, institution_name: str, year: int) -> int:
        if exam_mode not in self.VALID_MODES:
            raise ValueError("exam_mode must be 'post-utme' or 'jupeb'")
        supabase = get_supabase_client()
        inst = supabase.table("institutions").select("id").eq("name", institution_name).limit(1).execute()
        if not inst.data:
            raise ValueError(f"Institution '{institution_name}' not found")
        institution_id = inst.data[0]["id"]
        off = (
            supabase.table("institution_exam_offerings")
            .select("id")
            .eq("institution_id", institution_id)
            .eq("exam_mode", exam_mode)
            .eq("year", year)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        if not off.data:
            raise ValueError(f"No active offering for {institution_name} ({exam_mode}, {year})")
        return off.data[0]["id"]

    def list_subjects(self, exam_mode: str, institution_name: str, year: int) -> List[str]:
        offering_id = self._get_offering_id(exam_mode, institution_name, year)
        rows = (
            get_supabase_client()
            .table("institution_subjects")
            .select("subject_name")
            .eq("offering_id", offering_id)
            .order("subject_name")
            .execute()
            .data
        )
        return [r["subject_name"] for r in rows]

    def list_topics(self, exam_mode: str, institution_name: str, year: int, subject: str) -> List[str]:
        offering_id = self._get_offering_id(exam_mode, institution_name, year)
        sub = (
            get_supabase_client()
            .table("institution_subjects")
            .select("id")
            .eq("offering_id", offering_id)
            .eq("subject_name", subject)
            .limit(1)
            .execute()
        )
        if not sub.data:
            raise ValueError(f"Subject '{subject}' not available for {institution_name}")
        subject_id = sub.data[0]["id"]
        rows = (
            get_supabase_client()
            .table("institution_topics")
            .select("topic_name")
            .eq("institution_subject_id", subject_id)
            .order("topic_name")
            .execute()
            .data
        )
        topics = [r["topic_name"] for r in rows]
        return ["All Topics"] + topics

    def list_generated_questions(
        self,
        exam_mode: str,
        institution_name: str,
        year: int,
        subject: str,
        topic: Optional[str] = None,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        query = (
            get_supabase_client()
            .table("institution_generated_questions")
            .select("*")
            .eq("exam_mode", exam_mode)
            .eq("institution_name", institution_name)
            .eq("year", year)
            .eq("subject", subject)
        )
        if topic and topic.lower() != "all topics":
            query = query.eq("topic", topic)
        return query.order("created_at", desc=True).limit(limit).execute().data

