from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import anthropic

from app.config import get_settings
from app.db import get_supabase_client


@dataclass
class TopicIngestionResult:
    exam: str
    year: int
    subject: str
    normalized_topics: List[str]
    inserted_count: int
    skipped_count: int
    subject_created: bool


class TopicIngestionService:
    """Normalize and upsert syllabus-grade topics into syllabus_topics."""

    def __init__(self, model: Optional[str] = None) -> None:
        settings = get_settings()
        self.model = model or settings.anthropic_model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.supabase = get_supabase_client()

    def _get_exam_id(self, exam: str) -> Optional[int]:
        res = self.supabase.table("exams").select("id").eq("name", exam.upper()).limit(1).execute()
        if not res.data:
            return None
        return res.data[0]["id"]

    def _get_or_create_subject_id(self, exam_id: int, subject: str, create_if_missing: bool) -> tuple[Optional[int], bool]:
        res = (
            self.supabase.table("subjects")
            .select("id")
            .eq("exam_id", exam_id)
            .eq("name", subject)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]["id"], False
        if not create_if_missing:
            return None, False
        created = self.supabase.table("subjects").insert({"exam_id": exam_id, "name": subject}).execute()
        if not created.data:
            return None, False
        return created.data[0]["id"], True

    def _normalize_topics_with_claude(
        self,
        exam: str,
        year: int,
        subject: str,
        raw_topics: List[str],
        source_text: Optional[str],
    ) -> List[str]:
        raw_json = json.dumps(raw_topics, ensure_ascii=True)
        source_excerpt = (source_text or "").strip()
        if len(source_excerpt) > 16000:
            source_excerpt = source_excerpt[:16000]

        prompt = f"""
You are cleaning exam syllabus topics for database storage.

Task:
1) Normalize topic names for {exam.upper()} {year} {subject}.
2) Remove duplicates and near-duplicates.
3) Keep official/neutral naming (no numbering or bullet prefixes).
4) Return only topics relevant to {subject}.
5) Output JSON only.

Input raw_topics JSON:
{raw_json}

Optional source text:
{source_excerpt if source_excerpt else "N/A"}

Return exactly:
{{
  "topics": ["Topic A", "Topic B"]
}}
""".strip()

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1200,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json", "", 1).strip()

        parsed: Dict[str, Any] = json.loads(text)
        topics = parsed.get("topics", [])
        if not isinstance(topics, list):
            return []

        clean_topics: List[str] = []
        seen = set()
        for item in topics:
            if not isinstance(item, str):
                continue
            topic = " ".join(item.split()).strip()
            if not topic:
                continue
            key = topic.casefold()
            if key in seen:
                continue
            seen.add(key)
            clean_topics.append(topic)
        return clean_topics

    def ingest_topics(
        self,
        exam: str,
        year: int,
        subject: str,
        raw_topics: List[str],
        source_text: Optional[str] = None,
        source_url: Optional[str] = None,
        create_subject_if_missing: bool = False,
    ) -> TopicIngestionResult:
        exam_id = self._get_exam_id(exam)
        if not exam_id:
            raise ValueError(f"Exam '{exam}' not found in exams table")

        subject_id, created_subject = self._get_or_create_subject_id(exam_id, subject, create_subject_if_missing)
        if not subject_id:
            raise ValueError(
                f"Subject '{subject}' not found under exam '{exam.upper()}'. "
                "Set create_subject_if_missing=true to create it automatically."
            )

        normalized = self._normalize_topics_with_claude(
            exam=exam,
            year=year,
            subject=subject,
            raw_topics=raw_topics,
            source_text=source_text,
        )
        if not normalized:
            raise ValueError("Claude returned no valid topics to ingest")

        # Existing topics for skip statistics.
        existing_rows = (
            self.supabase.table("syllabus_topics")
            .select("topic_name")
            .eq("subject_id", subject_id)
            .eq("year", year)
            .execute()
            .data
        )
        existing = {row["topic_name"].casefold() for row in existing_rows}

        payload = [
            {
                "subject_id": subject_id,
                "topic_name": topic,
                "year": year,
            }
            for topic in normalized
        ]
        self.supabase.table("syllabus_topics").upsert(
            payload,
            on_conflict="subject_id,topic_name,year",
        ).execute()

        inserted_count = sum(1 for topic in normalized if topic.casefold() not in existing)
        skipped_count = len(normalized) - inserted_count

        # Best-effort audit row. Does nothing if table does not exist.
        try:
            self.supabase.table("generation_history").insert(
                {
                    "exam": exam.upper(),
                    "year": year,
                    "subject": subject,
                    "difficulty": "easy",
                    "topic": "TOPIC_INGESTION",
                    "count_requested": len(raw_topics) + (1 if source_text else 0),
                    "count_generated": inserted_count,
                    "count_failed": skipped_count,
                    "api_calls": 1,
                    "status": "success",
                    "error_message": f"source_url={source_url}" if source_url else None,
                    "generated_by": "topic_ingestion",
                }
            ).execute()
        except Exception:
            pass

        return TopicIngestionResult(
            exam=exam.upper(),
            year=year,
            subject=subject,
            normalized_topics=normalized,
            inserted_count=inserted_count,
            skipped_count=skipped_count,
            subject_created=created_subject,
        )

