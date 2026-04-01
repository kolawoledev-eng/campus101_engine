#!/usr/bin/env python3
"""
Import MCQs from a blyr-style Supabase project into grade9 `past_questions`.

Source (read): set BLYR_SUPABASE_URL and BLYR_SUPABASE_SERVICE_KEY (or BLYR_SUPABASE_ANON_KEY).
Destination (write): SUPABASE_URL and SUPABASE_SERVICE_KEY (same as the grade9 API).

Expected blyr tables: examtype, examyear, subject, question, option.

Diagrams: blyr typically stores a public URL in `question.image` (see blyr exam practice UIs).
That value is copied into grade9 `past_questions.image_url`. If your source uses path-only
URLs, set `BLYR_PUBLIC_IMAGE_BASE` (no trailing slash) so paths like `/storage/v1/...`
resolve to a full HTTPS URL.

Example (dry run):

  cd engine && \\
    BLYR_SUPABASE_URL=... BLYR_SUPABASE_SERVICE_KEY=... \\
    SUPABASE_URL=... SUPABASE_SERVICE_KEY=... \\
    python3 scripts/import_blyr_past_questions.py --exam WAEC --dry-run

Example (one subject, one year):

  python3 scripts/import_blyr_past_questions.py --exam JAMB --subject-id 12 --year 2023
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys


def _page_size_type(value: str) -> int:
    """argparse `ge`/`le` need Python 3.11+; validate range for 3.9 compatibility."""
    v = int(value)
    if v < 50 or v > 1000:
        raise argparse.ArgumentTypeError("page-size must be between 50 and 1000")
    return v
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from supabase import Client, create_client

from app.features.practice.past_ingest import insert_past_questions_batch

_HTML = re.compile(r"<[^>]+>")


def _strip_html(s: str) -> str:
    t = _HTML.sub(" ", s or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _image_url_from_blyr_question(q: Dict[str, Any]) -> Optional[str]:
    """Map blyr `question` row fields to a single HTTPS URL for `past_questions.image_url`."""
    base = os.getenv("BLYR_PUBLIC_IMAGE_BASE", "").strip().rstrip("/")
    for key in ("image", "image_url", "question_image", "diagram_url", "question_image_url"):
        v = q.get(key)
        if v is None:
            continue
        s = str(v).strip()
        if not s or s.lower() in ("null", "none"):
            continue
        if s.startswith("http://") or s.startswith("https://"):
            return s
        if base:
            if s.startswith("/"):
                return f"{base}{s}"
            return f"{base}/{s.lstrip('/')}"
    return None


def _difficulty_for_id(qid: int) -> str:
    return ("easy", "medium", "hard")[abs(qid) % 3]


def _syllabus_alignment(exam: str, calendar_year: int, subject_name: str, topic: str) -> str:
    """Same style as generated_questions.syllabus_alignment (exam + year + subject + topic)."""
    return f"{exam.strip().upper()} {int(calendar_year)} {subject_name.strip()}: {topic.strip()}".strip()


def _option_sort_key(o: Dict[str, Any]) -> Tuple[int, str]:
    oid = o.get("option_id")
    if oid is None:
        oid = o.get("id")
    try:
        oi = int(oid) if oid is not None else 0
    except (TypeError, ValueError):
        oi = 0
    return (oi, str(o.get("option_text") or ""))


def _build_row(
    *,
    exam: str,
    calendar_year: int,
    subject_name: str,
    q: Dict[str, Any],
    options: Sequence[Dict[str, Any]],
    topic_default: str,
    source_prefix: str,
) -> Optional[Dict[str, Any]]:
    qid = q.get("question_id")
    if qid is None:
        return None
    raw_text = q.get("question_text") or q.get("question_body") or ""
    text = _strip_html(str(raw_text))
    if not text or text.lower() == "null":
        return None

    opts = sorted(list(options), key=_option_sort_key)
    if len(opts) != 4:
        return None
    letters = []
    correct: Optional[str] = None
    for i, o in enumerate(opts):
        letter = ("A", "B", "C", "D")[i]
        letters.append(letter)
        is_c = o.get("is_correct")
        if is_c is True or str(is_c).lower() in ("true", "1", "t"):
            if correct is not None:
                return None
            correct = letter
    if correct is None:
        return None

    option_texts = [str(o.get("option_text") or "").strip() for o in opts]
    if any(not t for t in option_texts):
        return None

    img = _image_url_from_blyr_question(q)
    return {
        "exam": exam.strip().upper(),
        "year": int(calendar_year),
        "subject": subject_name.strip(),
        "difficulty": _difficulty_for_id(int(qid)),
        "topic": topic_default,
        "question_text": text,
        "option_a": option_texts[0],
        "option_b": option_texts[1],
        "option_c": option_texts[2],
        "option_d": option_texts[3],
        "correct_answer": correct,
        "explanation": None,
        "image_url": img,
        "source_label": f"{source_prefix}:{qid}",
        "learning_outcomes": [],
        "syllabus_alignment": _syllabus_alignment(exam, calendar_year, subject_name, topic_default),
        "source_type": "past",
    }


def _load_clients() -> Tuple[Client, Client]:
    src_url = os.getenv("BLYR_SUPABASE_URL", "").strip()
    src_key = os.getenv("BLYR_SUPABASE_SERVICE_KEY", "").strip() or os.getenv(
        "BLYR_SUPABASE_ANON_KEY", ""
    ).strip()
    dst_url = os.getenv("SUPABASE_URL", "").strip()
    dst_key = os.getenv("SUPABASE_SERVICE_KEY", "").strip() or os.getenv("SUPABASE_ANON_KEY", "").strip()
    missing = []
    if not src_url:
        missing.append("BLYR_SUPABASE_URL")
    if not src_key:
        missing.append("BLYR_SUPABASE_SERVICE_KEY or BLYR_SUPABASE_ANON_KEY")
    if not dst_url:
        missing.append("SUPABASE_URL")
    if not dst_key:
        missing.append("SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY")
    if missing:
        raise SystemExit(f"Missing env: {', '.join(missing)}")
    return create_client(src_url, src_key), create_client(dst_url, dst_key)


def _resolve_exam_type_id(src: Client, exam: str, explicit: Optional[int]) -> int:
    if explicit is not None:
        return explicit
    rows = src.table("examtype").select("exam_type_id,name").execute().data or []
    want = exam.strip().upper()
    exact: List[int] = []
    fuzzy: List[int] = []
    for r in rows:
        name = str(r.get("name") or "").upper()
        eid = r.get("exam_type_id")
        if eid is None:
            continue
        if name == want:
            exact.append(int(eid))
        elif want in name or name in want:
            fuzzy.append(int(eid))
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise SystemExit(f"Ambiguous examtype name={exam!r}: {exact}")
    if len(fuzzy) == 1:
        return fuzzy[0]
    raise SystemExit(
        f"Could not resolve exam type for {exam!r}. Pass --exam-type-id. Rows: "
        + json.dumps(rows, default=str)[:500]
    )


def _year_filter_ids(src: Client, exam_type_id: int, year: Optional[int]) -> Optional[List[int]]:
    if year is None:
        return None
    rows = (
        src.table("examyear")
        .select("exam_year_id,year")
        .eq("exam_type_id", exam_type_id)
        .eq("year", year)
        .execute()
        .data
        or []
    )
    ids = [int(r["exam_year_id"]) for r in rows if r.get("exam_year_id") is not None]
    if not ids:
        raise SystemExit(f"No examyear row for exam_type_id={exam_type_id} year={year}")
    return ids


def _subject_names(src: Client) -> Dict[int, str]:
    rows = src.table("subject").select("subject_id,name").execute().data or []
    out: Dict[int, str] = {}
    for r in rows:
        sid = r.get("subject_id")
        if sid is None:
            continue
        out[int(sid)] = str(r.get("name") or "").strip() or f"subject_{sid}"
    return out


def _fetch_options_for_questions(src: Client, qids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    out: Dict[int, List[Dict[str, Any]]] = {q: [] for q in qids}
    chunk = 80
    for i in range(0, len(qids), chunk):
        part = qids[i : i + chunk]
        rows = (
            src.table("option")
            .select("*")
            .in_("question_id", part)
            .execute()
            .data
            or []
        )
        for r in rows:
            qid = r.get("question_id")
            if qid is None:
                continue
            qi = int(qid)
            out.setdefault(qi, []).append(r)
    return out


def _existing_source_labels(dst: Client, labels: List[str]) -> Set[str]:
    if not labels:
        return set()
    found: Set[str] = set()
    chunk = 100
    for i in range(0, len(labels), chunk):
        part = labels[i : i + chunk]
        rows = dst.table("past_questions").select("source_label").in_("source_label", part).execute().data or []
        for r in rows:
            sl = r.get("source_label")
            if sl:
                found.add(str(sl))
    return found


def _exam_year_calendar_map(src: Client, exam_type_id: int) -> Dict[int, int]:
    rows = src.table("examyear").select("exam_year_id,year").eq("exam_type_id", exam_type_id).execute().data or []
    out: Dict[int, int] = {}
    for r in rows:
        eid = r.get("exam_year_id")
        y = r.get("year")
        if eid is None or y is None:
            continue
        try:
            out[int(eid)] = int(y)
        except (TypeError, ValueError):
            continue
    return out


def run_import(
    *,
    exam: str,
    exam_type_id: Optional[int],
    subject_id: Optional[int],
    year: Optional[int],
    page_size: int,
    max_rows: Optional[int],
    dry_run: bool,
    topic_default: str,
    source_prefix: str,
) -> Dict[str, Any]:
    src, dst = _load_clients()
    etid = _resolve_exam_type_id(src, exam, exam_type_id)
    year_ids = _year_filter_ids(src, etid, year)
    names = _subject_names(src)
    year_by_ey = _exam_year_calendar_map(src, etid)

    stats = {
        "exam_type_id": etid,
        "pages": 0,
        "questions_seen": 0,
        "rows_built": 0,
        "skipped": 0,
        "inserted": 0,
        "dry_run": dry_run,
    }

    start = 0
    inserted_total = 0
    while True:
        q = src.table("question").select("*").eq("exam_type_id", etid)
        if subject_id is not None:
            q = q.eq("subject_id", subject_id)
        if year_ids is not None:
            q = q.in_("exam_year_id", year_ids)
        batch = q.range(start, start + page_size - 1).execute().data or []
        stats["pages"] += 1
        if not batch:
            break
        stats["questions_seen"] += len(batch)

        qids = []
        for row in batch:
            qid = row.get("question_id")
            if qid is not None:
                qids.append(int(qid))
        opt_map = _fetch_options_for_questions(src, qids)

        built: List[Dict[str, Any]] = []
        for qrow in batch:
            qid = qrow.get("question_id")
            sid = qrow.get("subject_id")
            ey = qrow.get("exam_year_id")
            if qid is None or sid is None:
                stats["skipped"] += 1
                continue
            subj = names.get(int(sid), str(sid))
            try:
                ey_int = int(ey)
            except (TypeError, ValueError):
                ey_int = 0
            cy = year_by_ey.get(ey_int, 2020)
            opts = opt_map.get(int(qid), [])
            row = _build_row(
                exam=exam,
                calendar_year=cy,
                subject_name=subj,
                q=qrow,
                options=opts,
                topic_default=topic_default,
                source_prefix=source_prefix,
            )
            if row is None:
                stats["skipped"] += 1
                continue
            built.append(row)

        stats["rows_built"] += len(built)
        labels = [r["source_label"] for r in built if r.get("source_label")]
        existing = _existing_source_labels(dst, labels)
        fresh = [r for r in built if r.get("source_label") not in existing]
        if max_rows is not None:
            remain = max_rows - inserted_total
            if remain <= 0:
                break
            fresh = fresh[:remain]

        if fresh and not dry_run:
            res = insert_past_questions_batch(dst, fresh)
            inserted_total += int(res.get("inserted") or 0)
            stats["errors"] = res.get("errors", [])
        elif fresh and dry_run:
            inserted_total += len(fresh)

        if max_rows is not None and inserted_total >= max_rows:
            break
        if len(batch) < page_size:
            break
        start += page_size

    stats["inserted"] = inserted_total
    return stats


def main() -> None:
    p = argparse.ArgumentParser(description="Import blyr questions into grade9 past_questions.")
    p.add_argument("--exam", default="WAEC", help="Target exam label (WAEC, JAMB, …) for past_questions.exam")
    p.add_argument("--exam-type-id", type=int, default=None, help="Override examtype.exam_type_id in source")
    p.add_argument("--subject-id", type=int, default=None, help="Only this blyr subject_id")
    p.add_argument("--year", type=int, default=None, help="Calendar year (filters examyear.year)")
    p.add_argument(
        "--page-size",
        type=_page_size_type,
        default=300,
        help="Rows per Supabase page (50–1000, default 300)",
    )
    p.add_argument("--max-rows", type=int, default=None, help="Stop after inserting this many new rows")
    p.add_argument("--topic-default", default=os.getenv("PAST_QUESTION_TOPIC_DEFAULT", "General"))
    p.add_argument("--source-prefix", default="blyr", help="source_label prefix before :question_id")
    p.add_argument("--dry-run", action="store_true", help="Resolve and count rows only; no insert")
    args = p.parse_args()

    out = run_import(
        exam=args.exam,
        exam_type_id=args.exam_type_id,
        subject_id=args.subject_id,
        year=args.year,
        page_size=args.page_size,
        max_rows=args.max_rows,
        dry_run=args.dry_run,
        topic_default=args.topic_default,
        source_prefix=args.source_prefix.strip() or "blyr",
    )
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
