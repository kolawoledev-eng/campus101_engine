"""
JAMB classroom: one revision page per syllabus topic, stored in classroom_topic_pages.
Claude runs only on admin generate (or explicit regen); GET endpoints are DB-only.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

import anthropic

from app.config import get_settings
from app.features.classroom.image_urls import is_allowed_diagram_url, subject_visual_hints
from app.features.classroom.repository import ClassroomTopicPagesRepository
from app.features.topics.repository import TopicsRepository
from app.services.study_notes import StudyNotesService

INPUT_TOKEN_PRICE_PER_1K = Decimal("0.003")
OUTPUT_TOKEN_PRICE_PER_1K = Decimal("0.015")
MAX_OUT = 4096


def _cost(inp: int, out: int) -> Decimal:
    return (Decimal(inp) / Decimal(1000)) * INPUT_TOKEN_PRICE_PER_1K + (
        Decimal(out) / Decimal(1000)
    ) * OUTPUT_TOKEN_PRICE_PER_1K


def _extract_json(raw: str) -> str:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        return m.group(1).strip()
    return raw


def _parse_sections(
    raw_text: str,
    min_need: int = 2,
    max_images_total: int = 8,
    min_images_total: int = 1,
    max_images_per_section: int = 2,
) -> List[Dict[str, Any]]:
    text = _extract_json(raw_text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from model: {e}") from e
    notes = payload.get("sections", [])
    if not isinstance(notes, list):
        raise ValueError("Invalid sections format")
    out: List[Dict[str, Any]] = []
    image_budget = max_images_total
    for item in notes:
        if not isinstance(item, dict):
            continue
        h = " ".join(str(item.get("heading", "")).split()).strip()
        b = str(item.get("body", "")).strip()
        if not h or len(b) < 60:
            continue
        row: Dict[str, Any] = {"heading": h, "body": b}
        imgs_raw = item.get("images")
        imgs: List[Dict[str, str]] = []
        if isinstance(imgs_raw, list) and image_budget > 0:
            for im in imgs_raw:
                if len(imgs) >= max_images_per_section:
                    break
                if not isinstance(im, dict):
                    continue
                u = str(im.get("url", "")).strip()
                cap = " ".join(str(im.get("caption", "")).split()).strip()
                if not u or not is_allowed_diagram_url(u):
                    continue
                imgs.append({"url": u, "caption": cap or "Illustration"})
                image_budget -= 1
                if image_budget <= 0:
                    break
        if imgs:
            row["images"] = imgs
        out.append(row)
    if len(out) < min_need:
        raise ValueError(f"Only {len(out)} sections, need at least {min_need}")
    total_imgs = sum(len(s["images"]) for s in out if isinstance(s.get("images"), list))
    if total_imgs < min_images_total:
        raise ValueError(
            f"This topic page must include at least {min_images_total} valid Wikimedia Commons image(s); "
            f"model returned {total_imgs}. Regenerate or retry."
        )
    return out


def ordered_syllabus_topics(exam: str, year: int, subject: str) -> List[str]:
    repo = TopicsRepository()
    rows = repo.list_topics(exam, year, subject)
    out: List[str] = []
    for r in rows:
        name = str(r.get("topic_name", "")).strip()
        if name and name != "All Topics":
            out.append(name)
    return out


class ClassroomSubjectPagesService:
    def __init__(self, model: Optional[str] = None) -> None:
        settings = get_settings()
        self.model = model or settings.anthropic_model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.pages_repo = ClassroomTopicPagesRepository()
        self._validator = StudyNotesService(model=self.model)

    def build_reader_payload(self, exam: str, year: int, subject: str) -> Dict[str, Any]:
        ex = exam.upper().strip()
        topics = ordered_syllabus_topics(ex, year, subject)
        db_rows = self.pages_repo.list_pages_for_subject(ex, year, subject)
        by_topic = {str(r["topic"]): r for r in db_rows}
        pages: List[Dict[str, Any]] = []
        for i, name in enumerate(topics, start=1):
            row = by_topic.get(name)
            pages.append(
                {
                    "sequence": i,
                    "topic": name,
                    "ready": row is not None,
                    "sections": row.get("sections") if row else None,
                }
            )
        ready_count = sum(1 for p in pages if p["ready"])
        return {
            "status": "success",
            "exam": ex,
            "year": year,
            "subject": subject,
            "topic_count": len(pages),
            "ready_count": ready_count,
            "pages": pages,
        }

    def _prompt(self, exam: str, year: int, subject: str, topic: str) -> str:
        hints = subject_visual_hints(subject)
        return f"""
You are helping Nigerian SS3 students preparing for {exam.upper()}.

Subject: **{subject}**
Syllabus topic (exact): **{topic}**
Exam year context: **{year}**

Write **one revision page** for this topic only — not the whole subject.

Audience: SS3 in Nigeria. Match the style of Nigerian syllabus guides and WAEC/JAMB-friendly textbooks:
short clear explanations, defined terms in plain language, and exam-relevant points. Use Nigerian classroom English.
Be syllabus-accurate; do not invent facts or laws.

Return **JSON only** (no markdown fences):
{{
  "sections": [
    {{
      "heading": "Short subheading",
      "body": "One or more paragraphs as a single string; use \\\\n\\\\n between paragraphs."
    }}
  ]
}}

Rules:
- Provide **4 to 6** sections (introduction, key ideas, definitions, exam tips, short recap — adapt to the topic).
- Total body text about **400–550 words** across all sections (one printed page feel).
- Escape quotes inside strings; valid JSON only.

- **Illustrations (required):** The page must include **at least one** valid educational image for this topic.
  Add an `"images"` array on the **one or two** sections where a visual helps most (often after introducing an idea):
  `"images": [ {{ "url": "https://upload.wikimedia.org/wikipedia/commons/thumb/.../File.png/800px-File.png", "caption": "Short label" }} ]`
- Use **only** direct **https://upload.wikimedia.org/** file URLs you are **confident exist** on Wikimedia Commons (no other hosts, no search pages).
- Subject ideas for **{subject}**: {hints}
- If no hyper-specific file exists, pick a **closely related** syllabus illustration (e.g. generic cell for a cell topic; number line or plot for Mathematics).
- **At most two** `"images"` entries per section; **at most eight** images in total across the whole page.
""".strip()

    def generate_one_topic(
        self,
        exam: str,
        year: int,
        subject: str,
        topic: str,
        sequence_number: int,
        generated_by: str = "admin",
    ) -> Dict[str, Any]:
        ex = exam.upper().strip()
        existing = self.pages_repo.get_page(ex, year, subject, topic)
        if existing:
            return {"status": "already_exists", "topic": topic, "page": existing}

        self._validator._validate_tree(ex, year, subject, topic)

        prompt = self._prompt(ex, year, subject, topic)
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_OUT,
            temperature=0.35,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
        if getattr(resp, "stop_reason", None) == "max_tokens":
            raise ValueError("Output truncated; retry or shorten prompt.")
        sections = _parse_sections(raw, min_need=3)
        for i, s in enumerate(sections, start=1):
            s["order"] = i

        cost = float(_cost(resp.usage.input_tokens, resp.usage.output_tokens))
        saved = self.pages_repo.upsert_page(
            exam=ex,
            year=year,
            subject=subject,
            topic=topic,
            sequence_number=sequence_number,
            sections=sections,
            total_in=resp.usage.input_tokens,
            total_out=resp.usage.output_tokens,
            total_cost=cost,
            generated_by=generated_by,
        )
        return {
            "status": "created",
            "topic": topic,
            "page": saved,
            "usage": {
                "input_tokens": resp.usage.input_tokens,
                "output_tokens": resp.usage.output_tokens,
                "total_cost": cost,
            },
        }

    def generate_whole_subject(
        self,
        exam: str,
        year: int,
        subject: str,
        skip_existing: bool = True,
        sleep_seconds: float = 1.0,
        max_topics: Optional[int] = None,
    ) -> Dict[str, Any]:
        import time

        ex = exam.upper().strip()
        topics = ordered_syllabus_topics(ex, year, subject)
        processed = 0
        skipped = 0
        failed = 0
        errors: List[Dict[str, Any]] = []

        for i, topic in enumerate(topics, start=1):
            if max_topics is not None and processed >= max_topics:
                break
            if skip_existing and self.pages_repo.get_page(ex, year, subject, topic):
                skipped += 1
                continue
            try:
                self.generate_one_topic(ex, year, subject, topic, i, generated_by="admin_batch")
                processed += 1
            except Exception as exc:
                failed += 1
                errors.append({"topic": topic, "sequence": i, "error": str(exc)})
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        return {
            "status": "success",
            "exam": ex,
            "year": year,
            "subject": subject,
            "processed": processed,
            "skipped": skipped,
            "failed": failed,
            "errors": errors,
        }
