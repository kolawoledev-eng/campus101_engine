"""
Question generator with Supabase persistence.

Usage:
    from question_generator_supabase import QuestionGeneratorSupabase

    gen = QuestionGeneratorSupabase()
    questions = gen.generate_and_save(
        exam="waec",
        year=2024,
        subject="Physics",
        difficulty="hard",
        topic="all topics",
        count=40,
        user_email="student@example.com",
    )
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import anthropic
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

# Lazy import to avoid circular issues when used standalone
def _quota_check(client, exam: str, year: int, subject: str, topic: str, difficulty: str, requested: int):
    from app.core.question_quota import allowed_new_generations_national

    return allowed_new_generations_national(client, exam, year, subject, topic, difficulty, requested)


INPUT_TOKEN_PRICE_PER_1K = Decimal("0.003")
OUTPUT_TOKEN_PRICE_PER_1K = Decimal("0.015")
VALID_DIFFICULTIES = {"easy", "medium", "hard"}


@dataclass
class UsageStats:
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: Decimal = Decimal("0")


class SupabaseConnection:
    """DB helper around Supabase client."""

    def __init__(self) -> None:
        supabase_url = os.getenv("SUPABASE_URL")
        # Service key preferred on backend; falls back to anon.
        supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        if not supabase_url or not supabase_key:
            raise ValueError("Missing SUPABASE_URL and/or SUPABASE_SERVICE_KEY (or SUPABASE_ANON_KEY)")
        self.client: Client = create_client(supabase_url, supabase_key)

    def get_exam_id(self, exam_name: str) -> Optional[int]:
        res = self.client.table("exams").select("id").eq("name", exam_name.upper()).limit(1).execute()
        return res.data[0]["id"] if res.data else None

    def get_subject_id(self, exam_id: int, subject_name: str) -> Optional[int]:
        res = (
            self.client.table("subjects")
            .select("id")
            .eq("exam_id", exam_id)
            .eq("name", subject_name)
            .limit(1)
            .execute()
        )
        return res.data[0]["id"] if res.data else None

    def get_topics_for_subject(self, subject_id: int, year: int) -> List[str]:
        res = (
            self.client.table("syllabus_topics")
            .select("topic_name")
            .eq("subject_id", subject_id)
            .eq("year", year)
            .execute()
        )
        return [row["topic_name"] for row in res.data]

    def get_existing_questions(
        self,
        exam: str,
        year: int,
        subject: str,
        difficulty: str,
        topic: Optional[str],
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        query = (
            self.client.table("generated_questions")
            .select("question_text,option_a,option_b,option_c,option_d,correct_answer")
            .eq("exam", exam.upper())
            .eq("year", year)
            .eq("subject", subject)
            .eq("difficulty", difficulty)
        )
        if topic:
            query = query.eq("topic", topic)
        return query.limit(limit).execute().data

    def get_rag_context(
        self,
        exam: str,
        year: int,
        subject: str,
        difficulty: str,
        topic: Optional[str],
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Prefer past_questions for RAG, then generated_questions."""
        fields = "question_text,option_a,option_b,option_c,option_d,correct_answer"
        out: List[Dict[str, Any]] = []
        try:
            q = (
                self.client.table("past_questions")
                .select(fields)
                .eq("exam", exam.upper())
                .eq("year", year)
                .eq("subject", subject)
                .eq("difficulty", difficulty)
            )
            if topic:
                q = q.eq("topic", topic)
            past = q.limit(limit).execute().data or []
            out.extend(past)
        except Exception:
            pass
        need = max(0, limit - len(out))
        if need:
            out.extend(self.get_existing_questions(exam, year, subject, difficulty, topic, limit=need))
        return out[:limit]

    def insert_question(self, payload: Dict[str, Any]) -> Optional[str]:
        res = self.client.table("generated_questions").insert(payload).execute()
        if not res.data:
            return None
        return res.data[0]["id"]

    def insert_question_set(self, payload: Dict[str, Any]) -> Optional[str]:
        res = self.client.table("question_sets").insert(payload).execute()
        if not res.data:
            return None
        return res.data[0]["id"]

    def insert_question_set_items(self, items: List[Dict[str, Any]]) -> None:
        if items:
            self.client.table("question_set_items").insert(items).execute()

    def insert_generation_history(self, payload: Dict[str, Any]) -> None:
        self.client.table("generation_history").insert(payload).execute()

    def get_or_create_user(self, email: str) -> str:
        existing = self.client.table("users").select("*").eq("email", email).limit(1).execute().data
        if existing:
            return existing[0]["id"]
        created = (
            self.client.table("users")
            .insert({"email": email, "full_name": email.split("@")[0]})
            .execute()
            .data
        )
        return created[0]["id"]

    def update_user_stats(self, email: str, questions_count: int, api_cost: Decimal) -> None:
        users = (
            self.client.table("users")
            .select("total_questions_generated,total_api_cost")
            .eq("email", email)
            .limit(1)
            .execute()
            .data
        )
        if not users:
            self.get_or_create_user(email)
            users = (
                self.client.table("users")
                .select("total_questions_generated,total_api_cost")
                .eq("email", email)
                .limit(1)
                .execute()
                .data
            )
        current = users[0]
        total_questions = int(current.get("total_questions_generated", 0)) + questions_count
        total_cost = Decimal(str(current.get("total_api_cost", 0))) + api_cost
        self.client.table("users").update(
            {
                "total_questions_generated": total_questions,
                "total_api_cost": float(total_cost),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("email", email).execute()


class QuestionGeneratorSupabase:
    """Generate questions with Claude and persist to Supabase."""

    def __init__(self, model: Optional[str] = None) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required in .env")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
        self.db = SupabaseConnection()
        self.usage = UsageStats()

    def validate_filters(self, exam: str, year: int, subject: str, difficulty: str) -> bool:
        if difficulty not in VALID_DIFFICULTIES:
            raise ValueError("difficulty must be one of: easy, medium, hard")
        exam_id = self.db.get_exam_id(exam)
        if not exam_id:
            raise ValueError(f"exam '{exam}' not found in exams table")
        subject_id = self.db.get_subject_id(exam_id, subject)
        if not subject_id:
            raise ValueError(f"subject '{subject}' not found under exam '{exam.upper()}'")
        topics = self.db.get_topics_for_subject(subject_id, year)
        if not topics:
            raise ValueError(f"no syllabus topics found for subject '{subject}' and year {year}")
        return True

    def get_topics(self, exam: str, year: int, subject: str) -> List[str]:
        exam_id = self.db.get_exam_id(exam)
        if not exam_id:
            return []
        subject_id = self.db.get_subject_id(exam_id, subject)
        if not subject_id:
            return []
        return self.db.get_topics_for_subject(subject_id, year)

    def _build_prompt(
        self,
        exam: str,
        year: int,
        subject: str,
        topic: str,
        difficulty: str,
        question_number: int,
        past_questions: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        guidance = {
            "easy": "Focus on core definitions and single-step recall/application.",
            "medium": "Use multi-step reasoning and concept application.",
            "hard": "Use integrated concepts, nuanced distractors, and deeper analysis.",
        }[difficulty]

        rag_context = ""
        if past_questions:
            compact = []
            for q in past_questions[:2]:
                compact.append(
                    {
                        "question": q.get("question_text"),
                        "A": q.get("option_a"),
                        "B": q.get("option_b"),
                        "C": q.get("option_c"),
                        "D": q.get("option_d"),
                        "correct": q.get("correct_answer"),
                    }
                )
            rag_context = f"\nREFERENCE STYLE CONTEXT (avoid copying):\n{json.dumps(compact, ensure_ascii=True)}\n"

        return f"""
Generate one multiple-choice question for {exam.upper()} {year} {subject}.

Settings:
- Question number: {question_number}
- Difficulty: {difficulty}
- Topic: {topic}
- Guideline: {guidance}

Requirements:
1) Return STRICT JSON only, no markdown.
2) Exactly 4 options (A/B/C/D), one unambiguous answer.
3) Accurate to subject curriculum.
4) Make distractors plausible.
5) Explanation should be concise but clear (80-200 words).
6) learning_outcomes should be 2-4 short bullet-like strings.
{rag_context}
JSON schema:
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
  "learning_outcomes": ["string", "string"],
  "syllabus_alignment": "string"
}}
""".strip()

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        in_cost = (Decimal(input_tokens) / Decimal(1000)) * INPUT_TOKEN_PRICE_PER_1K
        out_cost = (Decimal(output_tokens) / Decimal(1000)) * OUTPUT_TOKEN_PRICE_PER_1K
        return in_cost + out_cost

    def _validate_question_payload(self, data: Dict[str, Any]) -> bool:
        options = data.get("options", {})
        values = [options.get("A"), options.get("B"), options.get("C"), options.get("D")]
        return bool(
            isinstance(data.get("question"), str)
            and len(data["question"].strip()) > 15
            and all(isinstance(v, str) and v.strip() for v in values)
            and len(set(v.strip() for v in values)) == 4
            and data.get("correct_answer") in {"A", "B", "C", "D"}
            and isinstance(data.get("explanation"), str)
            and len(data["explanation"].strip()) >= 40
            and isinstance(data.get("learning_outcomes"), list)
            and len(data["learning_outcomes"]) >= 1
        )

    def generate_single_question(
        self,
        exam: str,
        year: int,
        subject: str,
        topic: str,
        difficulty: str,
        question_number: int,
        past_questions: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        prompt = self._build_prompt(
            exam=exam,
            year=year,
            subject=subject,
            topic=topic,
            difficulty=difficulty,
            question_number=question_number,
            past_questions=past_questions,
        )
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=1200,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}],
        )

        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json", "", 1).strip()
        data = json.loads(text)

        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        self.usage.input_tokens += in_tok
        self.usage.output_tokens += out_tok
        self.usage.total_cost += self._calculate_cost(in_tok, out_tok)

        if not self._validate_question_payload(data):
            return None
        return data

    def generate_and_save(
        self,
        exam: str,
        year: int,
        subject: str,
        difficulty: str,
        topic: str = "all topics",
        count: int = 40,
        user_email: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if count < 1 or count > 100:
            raise ValueError("count must be in range 1..100")
        self.validate_filters(exam, year, subject, difficulty)

        all_topics = self.get_topics(exam, year, subject)
        if topic != "all topics" and topic not in all_topics:
            raise ValueError(f"topic '{topic}' not found for {subject} {year}")

        chosen_topics = all_topics if topic == "all topics" else [topic]

        client = self.db.client
        if topic != "all topics":
            allowed, reason = _quota_check(
                client, exam.upper(), year, subject, topic, difficulty, count
            )
            if allowed == 0:
                raise ValueError(reason)
            effective_count = min(count, allowed)
        else:
            # Per-topic quota: sum how many we can still add across topics
            remaining_by_topic: Dict[str, int] = {}
            for t in chosen_topics:
                a, r = _quota_check(client, exam.upper(), year, subject, t, difficulty, count)
                remaining_by_topic[t] = a
            if sum(remaining_by_topic.values()) == 0:
                raise ValueError(
                    "Quota: no room left for any topic at this difficulty "
                    f"(max {100} per difficulty per topic, max {500} per topic across difficulties)."
                )
            effective_count = min(count, sum(remaining_by_topic.values()))

        generation_started = datetime.now(timezone.utc)
        generated_rows: List[Dict[str, Any]] = []
        failed = 0

        rag_topic = None if topic == "all topics" else topic
        rag_context = self.db.get_rag_context(
            exam=exam.upper(),
            year=year,
            subject=subject,
            difficulty=difficulty,
            topic=rag_topic,
            limit=5,
        )

        iteration = 0
        while len(generated_rows) < effective_count and iteration < effective_count + failed + 50:
            iteration += 1
            if topic == "all topics":
                pool = [t for t in chosen_topics if remaining_by_topic.get(t, 0) > 0]
                if not pool:
                    break
                question_topic = random.choice(pool)
            else:
                question_topic = chosen_topics[0]
            try:
                payload = self.generate_single_question(
                    exam=exam.upper(),
                    year=year,
                    subject=subject,
                    topic=question_topic,
                    difficulty=difficulty,
                    question_number=len(generated_rows) + 1,
                    past_questions=rag_context,
                )
            except Exception:
                payload = None

            if not payload:
                failed += 1
                continue

            if topic == "all topics":
                a2, r2 = _quota_check(
                    client, exam.upper(), year, subject, question_topic, difficulty, 1
                )
                if a2 == 0:
                    remaining_by_topic[question_topic] = 0
                    failed += 1
                    continue
                remaining_by_topic[question_topic] = max(0, remaining_by_topic.get(question_topic, 0) - 1)

            row = {
                "exam": exam.upper(),
                "year": year,
                "subject": subject,
                "difficulty": difficulty,
                "topic": question_topic,
                "question_number": len(generated_rows) + 1,
                "question_text": payload["question"],
                "option_a": payload["options"]["A"],
                "option_b": payload["options"]["B"],
                "option_c": payload["options"]["C"],
                "option_d": payload["options"]["D"],
                "correct_answer": payload["correct_answer"],
                "explanation": payload["explanation"],
                "learning_outcomes": payload.get("learning_outcomes", []),
                "syllabus_alignment": payload.get("syllabus_alignment"),
                "source_type": "generated",
            }
            question_id = self.db.insert_question(row)
            if question_id:
                row["id"] = question_id
                generated_rows.append(row)
            else:
                failed += 1

        elapsed_sec = (datetime.now(timezone.utc) - generation_started).total_seconds()
        total_tokens = self.usage.input_tokens + self.usage.output_tokens

        if generated_rows:
            qset_payload = {
                "exam": exam.upper(),
                "year": year,
                "subject": subject,
                "difficulty": difficulty,
                "topic": topic if topic != "all topics" else "All Topics",
                "question_count": len(generated_rows),
                "total_tokens_used": total_tokens,
                "total_cost": float(self.usage.total_cost),
                "generation_time_seconds": round(elapsed_sec, 2),
                "generated_by": user_email or "api",
            }
            set_id = self.db.insert_question_set(qset_payload)
            if set_id:
                items = [
                    {"question_set_id": set_id, "question_id": q["id"], "sequence_number": idx + 1}
                    for idx, q in enumerate(generated_rows)
                ]
                self.db.insert_question_set_items(items)

            history = {
                "exam": exam.upper(),
                "year": year,
                "subject": subject,
                "difficulty": difficulty,
                "topic": topic if topic != "all topics" else "All Topics",
                "count_requested": count,
                "count_generated": len(generated_rows),
                "count_failed": failed,
                "api_calls": count,
                "total_tokens": total_tokens,
                "total_cost": float(self.usage.total_cost),
                "generation_time_seconds": round(elapsed_sec, 2),
                "status": "success" if failed == 0 else "partial",
                "generated_by": user_email or "api",
            }
            self.db.insert_generation_history(history)

            if user_email:
                self.db.update_user_stats(user_email, len(generated_rows), self.usage.total_cost)

        return generated_rows


if __name__ == "__main__":
    generator = QuestionGeneratorSupabase()
    qs = generator.generate_and_save(
        exam="waec",
        year=2024,
        subject="Physics",
        difficulty="hard",
        topic="all topics",
        count=5,
        user_email="student@example.com",
    )
    print(f"Generated and saved: {len(qs)}")
