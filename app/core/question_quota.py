"""Quota rules: max 100 per difficulty per scope, max 500 total per (exam, subject, year, topic)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from supabase import Client

MAX_PER_DIFFICULTY = 100
MAX_TOTAL_PER_TOPIC = 500


def _count_table(
    client: Client,
    table: str,
    filters: Dict[str, Any],
) -> int:
    q = client.table(table).select("id", count="exact")
    for k, v in filters.items():
        q = q.eq(k, v)
    res = q.execute()
    return res.count or 0


def count_national_scope(client: Client, exam: str, year: int, subject: str, topic: str, difficulty: str) -> Dict[str, int]:
    exam_u = exam.upper()
    f = {"exam": exam_u, "year": year, "subject": subject, "topic": topic, "difficulty": difficulty}
    past = _count_table(client, "past_questions", f)
    gen = _count_table(client, "generated_questions", f)
    total = past + gen
    per_diff = past + gen  # same filter includes difficulty
    return {"past": past, "generated": gen, "total": total, "per_difficulty": per_diff}


def count_institution_scope(
    client: Client,
    exam_mode: str,
    institution_name: str,
    year: int,
    subject: str,
    topic: str,
    difficulty: str,
) -> Dict[str, int]:
    f = {
        "exam_mode": exam_mode,
        "institution_name": institution_name,
        "year": year,
        "subject": subject,
        "topic": topic,
        "difficulty": difficulty,
    }
    past = _count_table(client, "institution_past_questions", f)
    gen = _count_table(client, "institution_generated_questions", f)
    total = past + gen
    return {"past": past, "generated": gen, "total": total, "per_difficulty": total}


def total_across_difficulties_national(
    client: Client, exam: str, year: int, subject: str, topic: str
) -> int:
    """Sum counts for all difficulties for this topic (past + generated)."""
    exam_u = exam.upper()
    total = 0
    for diff in ("easy", "medium", "hard"):
        total += count_national_scope(client, exam_u, year, subject, topic, diff)["total"]
    return total


def total_across_difficulties_institution(
    client: Client,
    exam_mode: str,
    institution_name: str,
    year: int,
    subject: str,
    topic: str,
) -> int:
    total = 0
    for diff in ("easy", "medium", "hard"):
        total += count_institution_scope(client, exam_mode, institution_name, year, subject, topic, diff)["total"]
    return total


def allowed_new_generations_national(
    client: Client,
    exam: str,
    year: int,
    subject: str,
    topic: str,
    difficulty: str,
    requested: int,
) -> tuple[int, str]:
    """
    Returns (allowed_count, reason_if_zero).
    """
    exam_u = exam.upper()
    scope = count_national_scope(client, exam_u, year, subject, topic, difficulty)
    total_topic = total_across_difficulties_national(client, exam_u, year, subject, topic)

    if scope["per_difficulty"] >= MAX_PER_DIFFICULTY:
        return (
            0,
            f"Quota: already {scope['per_difficulty']} questions for {difficulty} "
            f"(max {MAX_PER_DIFFICULTY} per difficulty). No LLM call.",
        )
    if total_topic >= MAX_TOTAL_PER_TOPIC:
        return (
            0,
            f"Quota: already {total_topic} questions for this topic across difficulties "
            f"(max {MAX_TOTAL_PER_TOPIC}). No LLM call.",
        )

    room_diff = MAX_PER_DIFFICULTY - scope["per_difficulty"]
    room_total = MAX_TOTAL_PER_TOPIC - total_topic
    # room_total is across difficulties; new rows only add to current difficulty's per_diff and total_topic
    allowed = min(requested, room_diff, room_total)
    return (max(0, allowed), "")


def allowed_new_generations_institution(
    client: Client,
    exam_mode: str,
    institution_name: str,
    year: int,
    subject: str,
    topic: str,
    difficulty: str,
    requested: int,
) -> tuple[int, str]:
    scope = count_institution_scope(
        client, exam_mode, institution_name, year, subject, topic, difficulty
    )
    total_topic = total_across_difficulties_institution(
        client, exam_mode, institution_name, year, subject, topic
    )

    if scope["per_difficulty"] >= MAX_PER_DIFFICULTY:
        return (
            0,
            f"Quota: already {scope['per_difficulty']} questions for {difficulty} "
            f"(max {MAX_PER_DIFFICULTY}). No LLM call.",
        )
    if total_topic >= MAX_TOTAL_PER_TOPIC:
        return (
            0,
            f"Quota: already {total_topic} questions for this topic (max {MAX_TOTAL_PER_TOPIC}). No LLM call.",
        )

    room_diff = MAX_PER_DIFFICULTY - scope["per_difficulty"]
    room_total = MAX_TOTAL_PER_TOPIC - total_topic
    allowed = min(requested, room_diff, room_total)
    return (max(0, allowed), "")
