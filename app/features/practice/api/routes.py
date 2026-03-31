from __future__ import annotations

import hashlib
import os
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.admin_auth import verify_admin_key
from app.core.db import get_supabase_client
from app.features.practice.backfill import run_download_pack_backfill
from app.features.practice.bucket_ensure import run_ensure_national_buckets
from app.features.practice.past_ingest import insert_past_questions_batch
from app.schemas import BulkPastQuestionsRequest, EnsureBucketsRequest, PastQuestionRow

router = APIRouter(prefix="/api/practice", tags=["practice"])

_FIELDS = "id,question_text,option_a,option_b,option_c,option_d,correct_answer,explanation,topic,year,difficulty"

_WS = re.compile(r"\s+")


def _fingerprint_part(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    s = _WS.sub(" ", s)
    return s


def _question_fingerprint(row: Dict[str, Any]) -> str:
    """Stable hash so past vs generated duplicates (same stem/options) collapse to one card."""
    blob = "|".join(
        [
            _fingerprint_part(row.get("question_text")),
            _fingerprint_part(row.get("option_a")),
            _fingerprint_part(row.get("option_b")),
            _fingerprint_part(row.get("option_c")),
            _fingerprint_part(row.get("option_d")),
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _pack_row_fingerprint(row: Dict[str, Any]) -> str:
    """Offline pack spans multiple years — keep same stem in different years as separate cards."""
    blob = "|".join(
        [
            _fingerprint_part(row.get("question_text")),
            _fingerprint_part(row.get("option_a")),
            _fingerprint_part(row.get("option_b")),
            _fingerprint_part(row.get("option_c")),
            _fingerprint_part(row.get("option_d")),
            str(row.get("year", "")),
            _fingerprint_part(row.get("difficulty")),
            _fingerprint_part(row.get("topic")),
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _finalize_unique_past_then_generated(
    past: List[Dict[str, Any]],
    gen: List[Dict[str, Any]],
    limit: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Past-first: unique past up to [limit], then unique generated for the remainder.
    Drops duplicates within each list and across lists (generated that match a kept past row).
    """
    seen: Set[str] = set()
    out_past: List[Dict[str, Any]] = []
    for r in past:
        if len(out_past) >= limit:
            break
        fp = _question_fingerprint(r)
        if fp in seen:
            continue
        seen.add(fp)
        row = dict(r)
        row["source"] = "past"
        out_past.append(row)

    need = limit - len(out_past)
    out_gen: List[Dict[str, Any]] = []
    for r in gen:
        if len(out_gen) >= need:
            break
        fp = _question_fingerprint(r)
        if fp in seen:
            continue
        seen.add(fp)
        row = dict(r)
        row["source"] = "generated"
        out_gen.append(row)
    return out_past, out_gen


# Default off to avoid mobile timeouts and surprise Claude cost. Set DOWNLOAD_PACK_BACKFILL_DEFAULT=true on the host to opt in.
_download_bf_env = os.getenv("DOWNLOAD_PACK_BACKFILL_DEFAULT", "").strip().lower()
DOWNLOAD_PACK_BACKFILL_DEFAULT: bool = _download_bf_env in ("1", "true", "yes")


def _past_row_to_db(r: PastQuestionRow) -> Dict[str, Any]:
    return {
        "exam": r.exam.strip().upper(),
        "year": r.year,
        "subject": r.subject.strip(),
        "difficulty": r.difficulty,
        "topic": r.topic.strip(),
        "question_text": r.question_text.strip(),
        "option_a": r.option_a.strip(),
        "option_b": r.option_b.strip(),
        "option_c": r.option_c.strip(),
        "option_d": r.option_d.strip(),
        "correct_answer": r.correct_answer,
        "explanation": (r.explanation or "").strip() or None,
        "source_label": (r.source_label or "").strip() or None,
    }


@router.post("/admin/past-questions/bulk", dependencies=[Depends(verify_admin_key)])
async def bulk_ingest_past_questions(payload: BulkPastQuestionsRequest) -> Dict[str, Any]:
    """Admin: bulk insert licensed past MCQs into past_questions (header X-Admin-Key)."""
    if not payload.questions:
        return {"status": "success", "inserted": 0, "requested": 0, "errors": []}
    supabase = get_supabase_client()
    rows = [_past_row_to_db(q) for q in payload.questions]
    result = insert_past_questions_batch(supabase, rows)
    return {"status": "success", **result}


@router.post("/admin/ensure-buckets", dependencies=[Depends(verify_admin_key)])
async def ensure_national_buckets(payload: EnsureBucketsRequest) -> Dict[str, Any]:
    """Admin: top up each syllabus topic × difficulty toward target using AI generation (X-Admin-Key)."""
    supabase = get_supabase_client()
    return run_ensure_national_buckets(
        supabase,
        exam=payload.exam,
        year=payload.year,
        subject=payload.subject,
        target_per_difficulty=payload.target_per_difficulty,
        max_questions_to_generate=payload.max_questions_to_generate,
        topics_filter=payload.topics,
        user_email=payload.user_email,
    )


def _collect_bucket(
    supabase: Any,
    exam: str,
    year: int,
    subject: str,
    difficulty: str,
    limit: int,
    topic: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Prefer past_questions, then top up with generated_questions.
    Fetches extra rows from DB when needed so duplicates (same stem/options) do not eat slots.
    """
    fetch_cap = min(500, max(limit * 10, limit + 50))

    past_raw: List[Dict[str, Any]] = []
    try:
        q = (
            supabase.table("past_questions")
            .select(_FIELDS + ",source_label")
            .eq("exam", exam.upper())
            .eq("year", year)
            .eq("subject", subject)
            .eq("difficulty", difficulty)
        )
        if topic and topic.lower() != "all topics":
            q = q.eq("topic", topic)
        past_raw = q.limit(fetch_cap).execute().data or []
    except Exception:
        past_raw = []

    seen: Set[str] = set()
    past: List[Dict[str, Any]] = []
    for r in past_raw:
        if len(past) >= limit:
            break
        fp = _question_fingerprint(r)
        if fp in seen:
            continue
        seen.add(fp)
        past.append(dict(r))

    need = limit - len(past)
    gen: List[Dict[str, Any]] = []
    if need > 0:
        gen_raw: List[Dict[str, Any]] = []
        try:
            q2 = (
                supabase.table("generated_questions")
                .select(_FIELDS)
                .eq("exam", exam.upper())
                .eq("year", year)
                .eq("subject", subject)
                .eq("difficulty", difficulty)
            )
            if topic and topic.lower() != "all topics":
                q2 = q2.eq("topic", topic)
            gen_raw = q2.limit(fetch_cap).execute().data or []
        except Exception:
            gen_raw = []

        for r in gen_raw:
            if len(gen) >= need:
                break
            fp = _question_fingerprint(r)
            if fp in seen:
                continue
            seen.add(fp)
            gen.append(dict(r))

    for p in past:
        p["source"] = "past"
    for g in gen:
        g["source"] = "generated"
    return past, gen


def _merge_jamb_use_of_english_bucket(
    supabase: Any,
    exam: str,
    year: int,
    subject: str,
    difficulty: str,
    limit: int,
    topic: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    If packs were ingested as legacy JAMB subject name \"English\", merge them into Use of English.
    """
    past, gen = _collect_bucket(supabase, exam, year, subject, difficulty, limit, topic=topic)
    if exam.upper() != "JAMB" or subject != "Use of English":
        return past, gen
    total = len(past) + len(gen)
    if total >= limit:
        return past, gen
    need = limit - total
    past2, gen2 = _collect_bucket(supabase, exam, year, "English", difficulty, need, topic=topic)
    seen_fp = {_question_fingerprint(x) for x in past + gen}
    for row in past2:
        if len(past) + len(gen) >= limit:
            break
        fp = _question_fingerprint(row)
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        past.append(row)
    for row in gen2:
        if len(past) + len(gen) >= limit:
            break
        fp = _question_fingerprint(row)
        if fp in seen_fp:
            continue
        seen_fp.add(fp)
        gen.append(row)
    return past, gen


@router.get("/session")
async def practice_session(
    exam: str = Query(...),
    year: int = Query(...),
    subject: str = Query(...),
    difficulty: str = Query(...),
    topic: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> Dict[str, Any]:
    """
    Build a practice set: prefer rows from past_questions, then generated_questions.
    All returned questions are unique by stem+options fingerprint (past first, then generated).
    """
    try:
        supabase = get_supabase_client()
        exu = exam.upper()
        past, gen = _merge_jamb_use_of_english_bucket(
            supabase, exu, year, subject, difficulty, limit, topic=topic
        )
        past, gen = _finalize_unique_past_then_generated(past, gen, limit)

        combined = past + gen
        random.shuffle(combined)
        return {
            "status": "success",
            "count": len(combined),
            "past_count": len(past),
            "generated_count": len(gen),
            "questions": combined[:limit],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/download-pack")
async def download_pack(
    exam: str = Query(..., description="National exam code e.g. JAMB, WAEC"),
    subject: str = Query(...),
    years: str = Query(default="2024,2025,2026", description="Comma-separated years"),
    limit_per_year_difficulty: int = Query(default=120, ge=1, le=400),
    backfill: bool = Query(
        default=DOWNLOAD_PACK_BACKFILL_DEFAULT,
        description="If true and ANTHROPIC_API_KEY is set, generate questions via Claude when a bucket is below limit_per_year_difficulty. "
        "Server default from DOWNLOAD_PACK_BACKFILL_DEFAULT env (else false).",
    ),
    backfill_max_per_bucket: int = Query(
        default=10,
        ge=0,
        le=100,
        description="Max new questions to generate per (year × difficulty) in this request; 0 disables backfill.",
    ),
    backfill_total_cap: int = Query(
        default=60,
        ge=0,
        le=300,
        description="Stop generating after this many new questions total (across all buckets) in one request.",
    ),
) -> Dict[str, Any]:
    """
    Bulk-fetch questions for offline practice: easy, medium, hard × each year (past + generated).
    Optionally backfills sparse buckets with Claude before reading (see `backfill*` params).
    Client stores JSON on device; practice sessions sample locally (e.g. 40 per session).
    """
    try:
        year_list = [int(x.strip()) for x in years.split(",") if x.strip().isdigit()]
        if not year_list:
            raise HTTPException(status_code=400, detail="No valid years in `years`")
        supabase = get_supabase_client()
        ex = exam.upper()
        diffs = ("easy", "medium", "hard")
        combined: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        if not backfill:
            backfill_report: Dict[str, Any] = {
                "enabled": False,
                "ran": False,
                "reason": "backfill=false",
                "total_generated": 0,
                "per_bucket": [],
            }
        elif backfill_max_per_bucket <= 0 or backfill_total_cap <= 0:
            backfill_report = {
                "enabled": True,
                "ran": False,
                "reason": "backfill_max_per_bucket or backfill_total_cap is 0",
                "total_generated": 0,
                "per_bucket": [],
            }
        else:
            backfill_report = run_download_pack_backfill(
                supabase,
                exam=ex,
                subject=subject,
                years=year_list,
                limit_per_year_difficulty=limit_per_year_difficulty,
                backfill_max_per_bucket=backfill_max_per_bucket,
                backfill_total_cap=backfill_total_cap,
            )
            backfill_report["enabled"] = True

        for yr in year_list:
            for diff in diffs:
                past, gen = _merge_jamb_use_of_english_bucket(
                    supabase, ex, yr, subject, diff, limit_per_year_difficulty, topic=None
                )
                past, gen = _finalize_unique_past_then_generated(
                    past, gen, limit_per_year_difficulty
                )
                for row in past + gen:
                    fp = _pack_row_fingerprint(row)
                    if fp in seen:
                        continue
                    seen.add(fp)
                    combined.append(row)

        random.shuffle(combined)
        return {
            "status": "success",
            "exam": ex,
            "subject": subject,
            "years": year_list,
            "count": len(combined),
            "questions": combined,
            "backfill": backfill_report,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
