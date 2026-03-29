from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

import anthropic

from app.config import get_settings
from app.db import get_supabase_client

INPUT_TOKEN_PRICE_PER_1K = Decimal("0.003")
OUTPUT_TOKEN_PRICE_PER_1K = Decimal("0.015")

# Many Claude models cap completion at 8192; 6000 was too low for 20+ long cards → truncated JSON, no DB save.
STUDY_NOTES_MAX_OUTPUT_TOKENS = 8192


@dataclass
class StudyNotesResult:
    note_set_id: str
    exam: str
    year: int
    subject: str
    topic: str
    total_subtopics: int
    notes: List[Dict[str, Any]]
    input_tokens: int
    output_tokens: int
    total_cost: float


class StudyNotesService:
    def __init__(self, model: Optional[str] = None) -> None:
        settings = get_settings()
        self.model = model or settings.anthropic_model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.supabase = get_supabase_client()

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        in_cost = (Decimal(input_tokens) / Decimal(1000)) * INPUT_TOKEN_PRICE_PER_1K
        out_cost = (Decimal(output_tokens) / Decimal(1000)) * OUTPUT_TOKEN_PRICE_PER_1K
        return in_cost + out_cost

    def _validate_tree(self, exam: str, year: int, subject: str, topic: str) -> None:
        exam_res = self.supabase.table("exams").select("id").eq("name", exam.upper()).limit(1).execute()
        if not exam_res.data:
            raise ValueError(f"Exam '{exam}' not found")
        exam_id = exam_res.data[0]["id"]

        sub_res = (
            self.supabase.table("subjects")
            .select("id")
            .eq("exam_id", exam_id)
            .eq("name", subject)
            .limit(1)
            .execute()
        )
        if not sub_res.data:
            raise ValueError(f"Subject '{subject}' not found under exam '{exam.upper()}'")
        subject_id = sub_res.data[0]["id"]

        topic_res = (
            self.supabase.table("syllabus_topics")
            .select("id")
            .eq("subject_id", subject_id)
            .eq("year", year)
            .eq("topic_name", topic)
            .limit(1)
            .execute()
        )
        if not topic_res.data:
            raise ValueError(f"Topic '{topic}' not found for {subject} {year}")

    def _build_prompt(
        self,
        exam: str,
        year: int,
        subject: str,
        topic: str,
        min_subtopics: int,
        read_time_target_minutes: int,
    ) -> str:
        return f"""
You are an expert exam prep curriculum writer.

Create study notes for:
- Exam: {exam.upper()}
- Year: {year}
- Subject: {subject}
- Main topic: {topic}

Output must be JSON only and follow this exact schema:
{{
  "notes": [
    {{
      "subtopic": "string",
      "title": "string",
      "summary_text": "string",
      "key_points": ["5-8 concise bullet points"],
      "examiner_focus": "what examiners usually test in this area",
      "common_mistakes": ["3-5 mistakes learners make"],
      "memory_hook": "short mnemonic/memory aid",
      "quick_recap": "2-4 sentence rapid recap",
      "syllabus_alignment": "specific alignment note"
    }}
  ]
}}

Hard rules:
1) Return at least {min_subtopics} UNIQUE subtopics.
2) Each summary_text: **130-260 words** (strict). Longer prose will be cut off and break JSON — stay compact.
3) Valid JSON only: escape double quotes inside strings as \\", use \\n for newlines inside strings, no raw line breaks inside quoted strings.
4) Use official curriculum-style wording relevant to {exam.upper()}.
5) Keep notes practical and exam-focused.
6) No markdown fences inside the JSON; outer response may be raw JSON only.
""".strip()

    @staticmethod
    def _extract_json_text(raw_text: str) -> str:
        """Pull JSON from ```json ... ``` if present; otherwise use trimmed raw text."""
        raw = raw_text.strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            return m.group(1).strip()
        return raw

    def _parse_and_validate(self, raw_text: str, min_subtopics: int) -> List[Dict[str, Any]]:
        text = self._extract_json_text(raw_text)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(
                "Model returned invalid or incomplete JSON (often output was truncated mid-string). "
                "Retry once; if it persists, lower min_subtopics. "
                f"Parse error: {e}"
            ) from e
        notes = payload.get("notes", [])
        if not isinstance(notes, list):
            raise ValueError("Model returned invalid notes format")

        validated: List[Dict[str, Any]] = []
        seen = set()
        for idx, note in enumerate(notes, start=1):
            if not isinstance(note, dict):
                continue
            subtopic = " ".join(str(note.get("subtopic", "")).split()).strip()
            title = " ".join(str(note.get("title", "")).split()).strip()
            summary_text = str(note.get("summary_text", "")).strip()
            # Align with prompt (130-260 words); short floor avoids accepting truncated fragments.
            if not subtopic or not title or len(summary_text) < 200:
                continue
            key = subtopic.casefold()
            if key in seen:
                continue
            seen.add(key)

            key_points = note.get("key_points", [])
            if not isinstance(key_points, list):
                key_points = []
            common_mistakes = note.get("common_mistakes", [])
            if not isinstance(common_mistakes, list):
                common_mistakes = []

            words = len(summary_text.split())
            read_time = round(words / 180, 2)

            validated.append(
                {
                    "sequence_number": idx,
                    "subtopic": subtopic,
                    "title": title,
                    "summary_text": summary_text,
                    "key_points": key_points,
                    "examiner_focus": str(note.get("examiner_focus", "")).strip(),
                    "common_mistakes": common_mistakes,
                    "memory_hook": str(note.get("memory_hook", "")).strip(),
                    "quick_recap": str(note.get("quick_recap", "")).strip(),
                    "read_time_minutes": read_time,
                    "syllabus_alignment": str(note.get("syllabus_alignment", "")).strip(),
                }
            )

        if len(validated) < min_subtopics:
            raise ValueError(
                f"Generated {len(validated)} valid subtopics, below required minimum {min_subtopics}"
            )
        return validated

    def generate_and_save(
        self,
        exam: str,
        year: int,
        subject: str,
        topic: str,
        min_subtopics: int = 20,
        read_time_target_minutes: int = 3,
        user_email: Optional[str] = None,
        source_url: Optional[str] = None,
    ) -> StudyNotesResult:
        self._validate_tree(exam, year, subject, topic)

        prompt = self._build_prompt(
            exam=exam,
            year=year,
            subject=subject,
            topic=topic,
            min_subtopics=min_subtopics,
            read_time_target_minutes=read_time_target_minutes,
        )
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=STUDY_NOTES_MAX_OUTPUT_TOKENS,
            temperature=0.4,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
        if getattr(resp, "stop_reason", None) == "max_tokens":
            raise ValueError(
                "Claude hit the maximum output length; the JSON was likely incomplete. "
                "Retry once, or lower min_subtopics / ask for shorter cards per topic."
            )
        notes = self._parse_and_validate(raw, min_subtopics=min_subtopics)
        total_cost = self._calculate_cost(resp.usage.input_tokens, resp.usage.output_tokens)

        note_set_res = self.supabase.table("study_note_sets").insert(
            {
                "exam": exam.upper(),
                "year": year,
                "subject": subject,
                "topic": topic,
                "min_subtopics": min_subtopics,
                "generated_by": user_email or "api",
                "source_url": source_url,
                "read_time_target_minutes": read_time_target_minutes,
                "total_subtopics": len(notes),
                "total_tokens_used": resp.usage.input_tokens + resp.usage.output_tokens,
                "total_cost": float(total_cost),
                "status": "success",
            }
        ).execute()
        if not note_set_res.data:
            raise RuntimeError("Failed to create study note set")
        note_set_id = note_set_res.data[0]["id"]

        rows = []
        for note in notes:
            rows.append(
                {
                    "note_set_id": note_set_id,
                    "exam": exam.upper(),
                    "year": year,
                    "subject": subject,
                    "topic": topic,
                    "subtopic": note["subtopic"],
                    "sequence_number": note["sequence_number"],
                    "title": note["title"],
                    "summary_text": note["summary_text"],
                    "key_points": note["key_points"],
                    "examiner_focus": note["examiner_focus"],
                    "common_mistakes": note["common_mistakes"],
                    "memory_hook": note["memory_hook"],
                    "quick_recap": note["quick_recap"],
                    "read_time_minutes": note["read_time_minutes"],
                    "syllabus_alignment": note["syllabus_alignment"],
                }
            )
        self.supabase.table("study_notes").insert(rows).execute()

        try:
            self.supabase.table("generation_history").insert(
                {
                    "exam": exam.upper(),
                    "year": year,
                    "subject": subject,
                    "difficulty": "easy",
                    "topic": f"STUDY_NOTES::{topic}",
                    "count_requested": min_subtopics,
                    "count_generated": len(notes),
                    "count_failed": 0,
                    "api_calls": 1,
                    "total_tokens": resp.usage.input_tokens + resp.usage.output_tokens,
                    "total_cost": float(total_cost),
                    "status": "success",
                    "generated_by": user_email or "api",
                }
            ).execute()
        except Exception:
            pass

        return StudyNotesResult(
            note_set_id=note_set_id,
            exam=exam.upper(),
            year=year,
            subject=subject,
            topic=topic,
            total_subtopics=len(notes),
            notes=rows,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            total_cost=float(total_cost),
        )

