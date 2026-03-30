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
        # Shorter floor for poems / short texts; chapters are still substantive revision chunks.
        if not h or len(b) < 60:
            continue
        out.append({"heading": h, "body": b})
    if len(out) < min_need:
        raise ValueError(f"Only {len(out)} valid sections, need at least {min_need}")
    return out


class LiteratureSummaryService:
    def __init__(self, model: Optional[str] = None) -> None:
        settings = get_settings()
        self.model = model or settings.anthropic_model
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.repo = LiteratureRepository()

    def _prompt_part(self, title: str, author: str, part_label: str, instructions: str) -> str:
        return f"""
You are helping Nigerian SS3 students preparing for JAMB Literature in English.

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
- Each body should read like a textbook narrative summary (roughly ½–1 exam page per chapter).
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

    def generate_and_save(self, novel_id: int, generated_by: str = "admin") -> Dict[str, Any]:
        novel = self.repo.get_novel(novel_id)
        if not novel:
            raise ValueError("Novel not found")
        existing = self.repo.get_summary_for_novel(novel_id)
        if existing:
            return {"status": "already_exists", "novel_id": novel_id, "summary": existing}

        title = str(novel["title"])
        author = str(novel["author"])

        p1 = self._prompt_part(
            title,
            author,
            "Part 1 of 2 — chapter summaries (early → middle)",
            """Produce exactly **6** objects in `sections`. Each object is **one chapter** of a revision guide students read in order (like a study app: Chapter 1 of 12, Chapter 2 of 12, …).

For each chapter:
- **heading**: A short, evocative chapter title (2–6 words), e.g. "Dusk", "The Enticement". Do **not** write "Chapter 1" in the heading — only the title.
- **body**: 2–4 paragraphs of **flowing narrative summary** in Nigerian SS3 / JAMB-friendly English (clear, classroom English; Naira, WAEC/JAMB, school life only where natural). Cover the work **in sequence** from the opening through roughly the **middle** of the plot (or first half of stanzas for a poem). Name key characters and events accurately; do not invent scenes.

For a **short poem or non-fiction extract**, treat each chapter as a **thematic block** in reading order (still 6 items), not a fake long plot.

Do not include any copyright disclaimer in the JSON (the app shows it separately).""",
        )
        raw1, in1, out1 = self._call(p1)
        sec1 = _parse_sections(raw1, min_need=5)

        p2 = self._prompt_part(
            title,
            author,
            "Part 2 of 2 — chapter summaries (middle → end)",
            f"""Continue the **same revision guide** for the same work. Produce exactly **6** NEW objects in `sections` (chapters 7–12 in reading order).

Rules:
- **heading**: Short chapter title only (never "Chapter 7" as the whole heading).
- **body**: Continue the narrative from **after** where Part 1 stopped through the **ending**, resolution, and any epilogue. Weave in **themes, lessons, and exam-relevant points** inside the story-style paragraphs (no separate lecture-style section).
- Do **not** repeat Part 1 events or headings. No disclaimer text in JSON.

Part 1 chapter titles (do not reuse): {", ".join(s["heading"] for s in sec1[:6])}""",
        )
        raw2, in2, out2 = self._call(p2)
        sec2 = _parse_sections(raw2, min_need=5)

        combined = sec1 + sec2
        if len(combined) > 12:
            combined = combined[:12]
        if len(combined) < 6:
            raise ValueError(f"Only {len(combined)} chapters after merge, need at least 6")
        for i, s in enumerate(combined, start=1):
            s["order"] = i

        total_in = in1 + in2
        total_out = out1 + out2
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
