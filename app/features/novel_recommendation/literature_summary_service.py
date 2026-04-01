"""
One-time Claude generation per literature text; results stored in novel_summaries.
Public API reads only from DB — no repeat LLM calls after save.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import anthropic

from app.config import get_settings
from app.features.novel_recommendation.literature_repository import LiteratureRepository

INPUT_TOKEN_PRICE_PER_1K = Decimal("0.003")
OUTPUT_TOKEN_PRICE_PER_1K = Decimal("0.015")
MAX_OUT = 8192


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


def _paragraph_count(body: str) -> int:
    """Prefer blank-line breaks; fall back to single newlines if the model omits \\n\\n."""
    t = body.strip()
    chunks = re.split(r"\n\s*\n+", t)
    n = sum(1 for c in chunks if len(c.strip()) >= 40)
    if n >= 3:
        return n
    lines = [ln for ln in t.split("\n") if len(ln.strip()) >= 45]
    return max(n, len(lines))


def _parse_sections(raw_text: str, min_need: int) -> List[Dict[str, str]]:
    """Parse chapter-style objects: heading = short chapter title; body = narrative paragraphs."""
    text = _extract_json(raw_text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from model: {e}") from e
    notes = payload.get("sections", [])
    if not isinstance(notes, list):
        raise ValueError("Model returned invalid sections format")
    out: List[Dict[str, str]] = []
    for item in notes:
        if not isinstance(item, dict):
            continue
        h = " ".join(str(item.get("heading", "")).split()).strip()
        b = str(item.get("body", "")).strip()
        # Target 4–5 paragraphs per chapter; allow 3 for a naturally short beat (e.g. tight poem block).
        pc = _paragraph_count(b)
        if not h or len(b) < 320 or pc < 3:
            continue
        out.append({"heading": h, "body": b})
    if len(out) < min_need:
        raise ValueError(f"Only {len(out)} valid sections, need at least {min_need}")
    return out


def _clean_title(value: str) -> str:
    return " ".join(value.split()).strip()


class LiteratureSummaryService:
    def __init__(self, model: Optional[str] = None) -> None:
        settings = get_settings()
        self.model = model or settings.anthropic_model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.repo = LiteratureRepository()

    def _prompt_part(self, title: str, author: str, part_label: str, instructions: str) -> str:
        return f"""
You are helping Nigerian SS3 students preparing for Recommended Novels in English.

Work: **{title}** by **{author}**.

Audience: SS3 in Nigeria — write like a good Nigerian textbook / lesson note: clear paragraphs, logical sub-ideas,
and wording students hear in school. Use simple English; explain literary terms (e.g. metaphor, dramatic irony)
in one short phrase when they appear. Avoid exam-cram jargon stacks.

Be accurate to the text; do not invent plot or quotes you are unsure of.

{part_label}

{instructions}

Return **JSON only** (no markdown fences) with this shape:
{{
  "sections": [
    {{ "heading": "Short chapter title (e.g. Dusk, The Enticement — not the words Chapter 1)", "body": "Several paragraphs; use escaped newlines between paragraphs." }}
  ]
}}

Rules:
- Escape double quotes inside strings as \\".
- Each **body** must be **4–5 full paragraphs** for most chapters (aim for five where the plot beat is rich); use **3** only when the section is naturally short. Separate paragraphs with **two newlines** (`\\n\\n`) inside the JSON string. Do **not** use only one or two paragraphs per chapter.
- Each body should read like a textbook narrative summary (about one exam page when read aloud).
- JSON must be complete and valid.
""".strip()

    def _call(self, prompt: str) -> Tuple[str, int, int]:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_OUT,
            temperature=0.35,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text
        if getattr(resp, "stop_reason", None) == "max_tokens":
            raise ValueError("Output truncated (max_tokens); retry or split prompt further.")
        return raw, resp.usage.input_tokens, resp.usage.output_tokens

    def _generate_dynamic_sections(self, title: str, author: str) -> Tuple[List[Dict[str, str]], int, int]:
        prompt = self._prompt_part(
            title,
            author,
            "Full-book revision guide — dynamic chapter count",
            """Produce a complete, in-order revision guide in `sections`.

Choose a chapter count that fits the work naturally:
- Typical novel/drama: **8 to 20** chapters.
- Short poem / short extract: **4 to 8** thematic chapters.

For each chapter:
- `heading`: short chapter title only (do not write "Chapter 1" in the heading).
- `body`: 3–5 full narrative paragraphs (usually 4–5).

Cover the entire work from opening to ending in sequence without skipping major turns.
Do not include disclaimer text in JSON.""",
        )
        raw, inp, out = self._call(prompt)
        return _parse_sections(raw, min_need=4), inp, out

    def _summarize_source_chapter(
        self,
        work_title: str,
        author: str,
        chapter_number: int,
        chapter_title: str,
        source_text: str,
    ) -> Tuple[str, int, int]:
        clipped = source_text.strip()
        # Keep prompt sizes predictable; enough context for good summaries.
        if len(clipped) > 14000:
            clipped = clipped[:14000] + "\n\n[Truncated for prompt size]"
        prompt = f"""
You are helping Nigerian SS3 students preparing for Recommended Novels in English.

Work: **{work_title}** by **{author}**.
Current chapter: {chapter_number} — "{chapter_title}".

Task:
- Read the chapter source text below.
- Write a clean chapter summary in 3–5 full paragraphs (usually 4–5).
- Preserve factual events, sequence, and key literary signals.
- Keep the style textbook-friendly and exam-oriented, but narrative (not bullet points).
- Do not add copyright disclaimers or markdown.

Return JSON only:
{{
  "body": "paragraph 1\\n\\nparagraph 2\\n\\nparagraph 3"
}}

Chapter source:
\"\"\"
{clipped}
\"\"\"
""".strip()
        raw, inp, out = self._call(prompt)
        text = _extract_json(raw)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON while summarizing chapter {chapter_number}: {e}") from e
        body = str(payload.get("body", "")).strip()
        if len(body) < 220 or _paragraph_count(body) < 3:
            raise ValueError(f"Chapter {chapter_number} summary too short from model")
        return body, inp, out

    def _generate_from_source_chapters(
        self,
        title: str,
        author: str,
        source_chapters: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        sections: List[Dict[str, Any]] = []
        total_in = 0
        total_out = 0
        for row in source_chapters:
            num_raw = row.get("chapter_number")
            chapter_number = int(num_raw) if isinstance(num_raw, int) else int(str(num_raw or "0"))
            if chapter_number <= 0:
                continue
            chapter_title = _clean_title(str(row.get("chapter_title", "")).strip()) or f"Chapter {chapter_number}"
            source_text = str(row.get("source_text", "")).strip()
            if not source_text:
                continue
            body, inp, out = self._summarize_source_chapter(
                work_title=title,
                author=author,
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                source_text=source_text,
            )
            total_in += inp
            total_out += out
            sections.append(
                {
                    "order": chapter_number,
                    "chapter_number": chapter_number,
                    "heading": chapter_title,
                    "body": body,
                    "source": "approved_chapter_text",
                }
            )
        if not sections:
            raise ValueError("No valid approved source chapters found to summarize")
        return sections, total_in, total_out

    def generate_and_save(self, novel_id: int, generated_by: str = "admin") -> Dict[str, Any]:
        novel = self.repo.get_novel(novel_id)
        if not novel:
            raise ValueError("Novel not found")
        existing = self.repo.get_summary_for_novel(novel_id)
        if existing:
            return {"status": "already_exists", "novel_id": novel_id, "summary": existing}

        title = str(novel["title"])
        author = str(novel["author"])
        source_chapters = self.repo.list_source_chapters(novel_id)
        if source_chapters:
            combined, total_in, total_out = self._generate_from_source_chapters(
                title=title,
                author=author,
                source_chapters=source_chapters,
            )
        else:
            combined_raw, total_in, total_out = self._generate_dynamic_sections(
                title=title,
                author=author,
            )
            combined = []
            for i, s in enumerate(combined_raw, start=1):
                combined.append(
                    {
                        "order": i,
                        "chapter_number": i,
                        "heading": _clean_title(s.get("heading", "")),
                        "body": s.get("body", "").strip(),
                        "source": "llm_dynamic_outline",
                    }
                )

        if len(combined) < 4:
            raise ValueError(f"Only {len(combined)} chapters generated, need at least 4")

        cost = float(_cost(total_in, total_out))

        try:
            saved = self.repo.insert_summary(
                novel_id=novel_id,
                sections=combined,
                total_in=total_in,
                total_out=total_out,
                total_cost=cost,
                generated_by=generated_by,
            )
        except Exception:
            existing2 = self.repo.get_summary_for_novel(novel_id)
            if existing2:
                return {"status": "already_exists", "novel_id": novel_id, "summary": existing2}
            raise
        return {
            "status": "created",
            "novel_id": novel_id,
            "summary": saved,
            "usage": {"input_tokens": total_in, "output_tokens": total_out, "total_cost": cost},
        }
