from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.db import get_supabase_client


class StudyNotesRepository:
    def list_notes(
        self,
        exam: str,
        year: int,
        subject: str,
        topic: Optional[str] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        query = (
            get_supabase_client()
            .table("study_notes")
            .select("*")
            .eq("exam", exam.upper())
            .eq("year", year)
            .eq("subject", subject)
        )
        if topic:
            query = query.eq("topic", topic)
        return query.order("sequence_number").limit(limit).execute().data

    def get_note_set(self, note_set_id: str) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
        supabase = get_supabase_client()
        set_res = supabase.table("study_note_sets").select("*").eq("id", note_set_id).limit(1).execute()
        if not set_res.data:
            raise ValueError("Study note set not found")
        note_set = set_res.data[0]
        notes = (
            supabase.table("study_notes")
            .select("*")
            .eq("note_set_id", note_set_id)
            .order("sequence_number")
            .execute()
            .data
        )
        return note_set, notes

