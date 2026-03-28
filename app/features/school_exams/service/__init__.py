from __future__ import annotations

import json
import random
from decimal import Decimal
from typing import Any, Dict, List

import anthropic

from app.core.config import get_settings
from app.core.db import get_supabase_client
from app.core.question_quota import allowed_new_generations_institution
from app.features.school_exams.repository import SchoolExamsRepository

INPUT_TOKEN_PRICE_PER_1K = Decimal("0.003")
OUTPUT_TOKEN_PRICE_PER_1K = Decimal("0.015")


class SchoolQuestionService:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model
        self.repo = SchoolExamsRepository()
        self.supabase = get_supabase_client()

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        in_cost = (Decimal(input_tokens) / Decimal(1000)) * INPUT_TOKEN_PRICE_PER_1K
        out_cost = (Decimal(output_tokens) / Decimal(1000)) * OUTPUT_TOKEN_PRICE_PER_1K
        return float(in_cost + out_cost)

    def _prompt(
        self,
        exam_mode: str,
        institution_name: str,
        year: int,
        subject: str,
        topic: str,
        difficulty: str,
        n: int,
    ) -> str:
        return f"""
Generate one high-quality {exam_mode.upper()} question for {institution_name} ({year}) in {subject}.

Settings:
- Topic: {topic}
- Difficulty: {difficulty}
- Question number: {n}

Return strict JSON only:
{{
  "question": "string",
  "options": {{
    "A": "string",
    "B": "string",
    "C": "string",
    "D": "string"
  }},
  "correct_answer": "A|B|C|D",
  "explanation": "string",
  "learning_outcomes": ["string", "string"]
}}
""".strip()

    def generate_and_save(
        self,
        exam_mode: str,
        institution_name: str,
        year: int,
        subject: str,
        topic: str,
        difficulty: str,
        count: int,
        user_email: str | None,
    ) -> Dict[str, Any]:
        topics = self.repo.list_topics(exam_mode, institution_name, year, subject)
        valid_topics = [t for t in topics if t != "All Topics"]
        if topic.lower() == "all topics":
            chosen_pool = valid_topics
        else:
            if topic not in valid_topics:
                raise ValueError(f"Topic '{topic}' not available for {institution_name} {subject}")
            chosen_pool = [topic]

        sb = self.supabase
        if topic.lower() != "all topics":
            allowed, reason = allowed_new_generations_institution(
                sb, exam_mode, institution_name, year, subject, topic, difficulty, count
            )
            if allowed == 0:
                raise ValueError(reason)
            effective_count = min(count, allowed)
        else:
            remaining_by_topic: Dict[str, int] = {}
            for t in chosen_pool:
                a, _r = allowed_new_generations_institution(
                    sb, exam_mode, institution_name, year, subject, t, difficulty, count
                )
                remaining_by_topic[t] = a
            if sum(remaining_by_topic.values()) == 0:
                raise ValueError(
                    "Quota: no room left for any topic at this difficulty "
                    "(max 100 per difficulty per topic, max 500 per topic across difficulties)."
                )
            effective_count = min(count, sum(remaining_by_topic.values()))

        usage_in = 0
        usage_out = 0
        rows: List[Dict[str, Any]] = []

        set_row = self.supabase.table("institution_question_sets").insert(
            {
                "exam_mode": exam_mode,
                "institution_name": institution_name,
                "year": year,
                "subject": subject,
                "topic": topic if topic.lower() != "all topics" else "All Topics",
                "difficulty": difficulty,
                "question_count": effective_count,
                "generated_by": user_email or "api",
            }
        ).execute()
        if not set_row.data:
            raise RuntimeError("Failed to create institution question set")
        set_id = set_row.data[0]["id"]

        generated_rows = 0
        attempts = 0
        max_attempts = effective_count * 3 + 10
        while generated_rows < effective_count and attempts < max_attempts:
            attempts += 1
            if topic.lower() == "all topics":
                pool = [t for t in chosen_pool if remaining_by_topic.get(t, 0) > 0]
                if not pool:
                    break
                t = random.choice(pool)
            else:
                t = chosen_pool[0]

            a2, _ = allowed_new_generations_institution(
                sb, exam_mode, institution_name, year, subject, t, difficulty, 1
            )
            if a2 == 0:
                if topic.lower() == "all topics":
                    remaining_by_topic[t] = 0
                continue

            response = self.client.messages.create(
                model=self.model,
                max_tokens=1200,
                temperature=0.6,
                messages=[
                    {
                        "role": "user",
                        "content": self._prompt(
                            exam_mode,
                            institution_name,
                            year,
                            subject,
                            t,
                            difficulty,
                            generated_rows + 1,
                        ),
                    }
                ],
            )
            payload_text = response.content[0].text.strip()
            if payload_text.startswith("```"):
                payload_text = payload_text.strip("`").replace("json", "", 1).strip()
            data = json.loads(payload_text)
            usage_in += response.usage.input_tokens
            usage_out += response.usage.output_tokens
            row = {
                "question_set_id": set_id,
                "exam_mode": exam_mode,
                "institution_name": institution_name,
                "year": year,
                "subject": subject,
                "topic": t,
                "difficulty": difficulty,
                "question_number": generated_rows + 1,
                "question_text": data["question"],
                "option_a": data["options"]["A"],
                "option_b": data["options"]["B"],
                "option_c": data["options"]["C"],
                "option_d": data["options"]["D"],
                "correct_answer": data["correct_answer"],
                "explanation": data["explanation"],
                "learning_outcomes": data.get("learning_outcomes", []),
                "source_type": "generated",
            }
            insert = self.supabase.table("institution_generated_questions").insert(row).execute()
            if insert.data:
                row["id"] = insert.data[0]["id"]
                rows.append(row)
                generated_rows += 1
                if topic.lower() == "all topics":
                    remaining_by_topic[t] = max(0, remaining_by_topic.get(t, 0) - 1)

        total_cost = self._cost(usage_in, usage_out)
        self.supabase.table("institution_question_sets").update(
            {
                "total_tokens_used": usage_in + usage_out,
                "total_cost": total_cost,
                "question_count": len(rows),
            }
        ).eq("id", set_id).execute()

        return {
            "status": "success",
            "question_set_id": set_id,
            "count": len(rows),
            "questions": rows,
            "usage": {"input_tokens": usage_in, "output_tokens": usage_out, "total_cost": total_cost},
        }
