from __future__ import annotations

from typing import Any, Dict

from app.core.db import get_supabase_client


class TopicsRepository:
    def list_exams(self) -> list[Dict[str, Any]]:
        return get_supabase_client().table("exams").select("*").order("name").execute().data

    def _get_exam_id(self, exam: str) -> int:
        res = get_supabase_client().table("exams").select("id").eq("name", exam.upper()).limit(1).execute()
        if not res.data:
            raise ValueError(f"Exam '{exam}' not found")
        return res.data[0]["id"]

    def list_subjects(self, exam: str) -> list[Dict[str, Any]]:
        exam_id = self._get_exam_id(exam)
        return (
            get_supabase_client()
            .table("subjects")
            .select("id,name")
            .eq("exam_id", exam_id)
            .order("name")
            .execute()
            .data
        )

    def list_topics(self, exam: str, year: int, subject: str) -> list[Dict[str, Any]]:
        exam_id = self._get_exam_id(exam)
        sub = (
            get_supabase_client()
            .table("subjects")
            .select("id")
            .eq("exam_id", exam_id)
            .eq("name", subject)
            .limit(1)
            .execute()
        )
        if not sub.data:
            raise ValueError(f"Subject '{subject}' not found under '{exam}'")
        subject_id = sub.data[0]["id"]
        topics = (
            get_supabase_client()
            .table("syllabus_topics")
            .select("id,topic_name,year")
            .eq("subject_id", subject_id)
            .eq("year", year)
            .order("topic_name")
            .execute()
            .data
        )
        return [{"id": 0, "topic_name": "All Topics", "year": year}] + topics

