from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

import anthropic

from app.config import get_settings
from app.db import get_supabase_client
from app.features.classroom.image_urls import is_allowed_diagram_url, subject_visual_hints

INPUT_TOKEN_PRICE_PER_1K = Decimal("0.003")
OUTPUT_TOKEN_PRICE_PER_1K = Decimal("0.015")

# Claude caps completion around 8192 tokens; 20+ long cards in one JSON still truncates.
# We request subtopics in chunks so each response completes, then merge before DB insert.
STUDY_NOTES_MAX_OUTPUT_TOKENS = 8192
STUDY_NOTES_CHUNK_SIZE = 6


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
        batch_count: int,
        read_time_target_minutes: int,
        covered_subtopics: List[str],
    ) -> str:
        covered_block = ""
        if covered_subtopics:
            # Keep prompt small; model only needs to avoid dupes.
            tail = covered_subtopics[-60:]
            covered_block = (
                "\n\nSubtopics already covered in earlier batches — do NOT repeat or closely paraphrase:\n- "
                + "\n- ".join(tail)
            )
        vhints = subject_visual_hints(subject)
        return f"""
You are an expert exam prep curriculum writer.

Create study notes for:
- Exam: {exam.upper()}
- Year: {year}
- Subject: {subject}
- Main topic: {topic}

This batch only: produce **exactly {batch_count}** distinct subtopics under the main topic above.
Target read depth: about {read_time_target_minutes} minutes per card (compact prose).
{covered_block}

Output must be JSON only and follow this exact schema:
{{
  "notes": [
    {{
      "subtopic": "string",
      "title": "string",
      "summary_text": "string",
      "images": [ {{ "url": "https://upload.wikimedia.org/...", "caption": "short label for students" }} ],
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
1) The "notes" array must contain **at least {batch_count}** objects (distinct subtopics).
2) Each summary_text: **120-200 words** (strict). Stay compact so the JSON completes in one response.
3) **Images (required):** Every note must include **at least one** object in `"images"` with a direct **https://upload.wikimedia.org/** URL (Wikimedia Commons file only) and a short caption. Use **only** URLs you are confident exist. Ideas for **{subject}**: {vhints}
   At most **two** images per note. Place the illustration where it supports the subtopic (students learn faster with visuals).
4) Valid JSON only: escape double quotes inside strings as \\", use \\n for newlines inside strings, no raw line breaks inside quoted strings.
5) Use official curriculum-style wording relevant to {exam.upper()}.
6) Keep notes practical and exam-focused.
7) No markdown fences inside the JSON; outer response may be raw JSON only.
""".strip()

    @staticmethod
    def _extract_json_text(raw_text: str) -> str:
        """Pull JSON from ```json ... ``` if present; otherwise use trimmed raw text."""
        raw = raw_text.strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if m:
            return m.group(1).strip()
        return raw

    def _parse_and_validate(self, raw_text: str, min_required: int) -> List[Dict[str, Any]]:
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

            imgs_raw = note.get("images")
            images: List[Dict[str, str]] = []
            if isinstance(imgs_raw, list):
                for im in imgs_raw:
                    if len(images) >= 2:
                        break
                    if not isinstance(im, dict):
                        continue
                    u = str(im.get("url", "")).strip()
                    cap = " ".join(str(im.get("caption", "")).split()).strip()
                    if not u or not is_allowed_diagram_url(u):
                        continue
                    images.append({"url": u, "caption": cap or "Illustration"})
            if len(images) < 1:
                continue

            words = len(summary_text.split())
            read_time = round(words / 180, 2)

            validated.append(
                {
                    "sequence_number": idx,
                    "subtopic": subtopic,
                    "title": title,
                    "summary_text": summary_text,
                    "images": images,
                    "key_points": key_points,
                    "examiner_focus": str(note.get("examiner_focus", "")).strip(),
                    "common_mistakes": common_mistakes,
                    "memory_hook": str(note.get("memory_hook", "")).strip(),
                    "quick_recap": str(note.get("quick_recap", "")).strip(),
                    "read_time_minutes": read_time,
                    "syllabus_alignment": str(note.get("syllabus_alignment", "")).strip(),
                }
            )

        if len(validated) < min_required:
            raise ValueError(
                f"Generated {len(validated)} valid subtopics, below required minimum {min_required}"
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

        accumulated: List[Dict[str, Any]] = []
        seen_subtopic: set[str] = set()
        total_in = 0
        total_out = 0
        api_calls = 0
        max_rounds = max(32, (min_subtopics // STUDY_NOTES_CHUNK_SIZE) + 8)

        while len(accumulated) < min_subtopics and api_calls < max_rounds:
            need = min(STUDY_NOTES_CHUNK_SIZE, min_subtopics - len(accumulated))
            if need <= 0:
                break
            covered = [n["subtopic"] for n in accumulated]
            prompt = self._build_prompt(
                exam=exam,
                year=year,
                subject=subject,
                topic=topic,
                batch_count=need,
                read_time_target_minutes=read_time_target_minutes,
                covered_subtopics=covered,
            )
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=STUDY_NOTES_MAX_OUTPUT_TOKENS,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}],
            )
            api_calls += 1
            total_in += resp.usage.input_tokens
            total_out += resp.usage.output_tokens
            raw = resp.content[0].text
            if getattr(resp, "stop_reason", None) == "max_tokens":
                raise ValueError(
                    "Claude hit the maximum output length on a batch. "
                    "Retry; if it persists, reduce min_subtopics or we can lower STUDY_NOTES_CHUNK_SIZE."
                )
            batch = self._parse_and_validate(raw, min_required=need)
            before = len(accumulated)
            for item in batch:
                key = str(item.get("subtopic", "")).casefold().strip()
                if not key or key in seen_subtopic:
                    continue
                seen_subtopic.add(key)
                accumulated.append(item)
            if len(accumulated) == before:
                raise ValueError(
                    "No new subtopics were added in this batch (duplicates or empty). "
                    "Try again or lower min_subtopics."
                )

        if len(accumulated) < min_subtopics:
            raise ValueError(
                f"After {api_calls} API call(s), only {len(accumulated)} distinct subtopics were generated; "
                f"needed {min_subtopics}."
            )

        # Trim if the model over-delivered on the last batch.
        if len(accumulated) > min_subtopics:
            accumulated = accumulated[:min_subtopics]

        for i, item in enumerate(accumulated, start=1):
            item["sequence_number"] = i

        total_cost = self._calculate_cost(total_in, total_out)

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
                "total_subtopics": len(accumulated),
                "total_tokens_used": total_in + total_out,
                "total_cost": float(total_cost),
                "status": "success",
            }
        ).execute()
        if not note_set_res.data:
            raise RuntimeError("Failed to create study note set")
        note_set_id = note_set_res.data[0]["id"]

        rows = []
        for note in accumulated:
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
                    "images": note.get("images") or [],
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
                    "count_generated": len(accumulated),
                    "count_failed": 0,
                    "api_calls": api_calls,
                    "total_tokens": total_in + total_out,
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
            total_subtopics=len(accumulated),
            notes=rows,
            input_tokens=total_in,
            output_tokens=total_out,
            total_cost=float(total_cost),
        )

