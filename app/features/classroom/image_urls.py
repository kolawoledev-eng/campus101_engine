"""Allow-list for diagram URLs embedded in classroom pages (public HTTPS only)."""

from __future__ import annotations

from urllib.parse import urlparse


def is_allowed_diagram_url(url: str) -> bool:
    """Accept direct Wikimedia Commons file URLs (stable for education)."""
    try:
        p = urlparse((url or "").strip())
        if p.scheme != "https":
            return False
        host = (p.hostname or "").lower()
        if host == "upload.wikimedia.org":
            return True
        # Rare: some tools return uppercase path-only; still require upload host
        return False
    except Exception:
        return False


def subject_supports_diagrams(subject: str) -> bool:
    """Deprecated for gating images — all subjects may include Commons illustrations."""
    s = (subject or "").casefold()
    return any(k in s for k in ("biology", "chemistry", "physics"))


def subject_visual_hints(subject: str) -> str:
    """One-line hints for the model when picking Wikimedia illustrations (upload.wikimedia.org only)."""
    s = (subject or "").casefold()
    if "biology" in s:
        return "e.g. labelled diagrams: cell, organ systems, ecology, genetics."
    if "chemistry" in s:
        return "e.g. apparatus, periodic trends, simple molecule/bonding diagrams, lab setup."
    if "physics" in s:
        return "e.g. circuits, motion/forces diagrams, waves, optics, simple apparatus."
    if "mathematics" in s or "math" in s or "further math" in s or "further mathematics" in s:
        return "e.g. graphs of functions, geometry (angles, shapes), coordinate plots, number lines, triangles."
    if "agric" in s or "agriculture" in s:
        return "e.g. farm tools, crop parts, simple animal husbandry or soil diagrams."
    if "geography" in s:
        return "e.g. maps, landforms, climate diagrams, simple cross-sections."
    if "economics" in s:
        return "e.g. simple supply/demand sketches, circular flow (if on Commons), basic charts."
    if "government" in s or "civic" in s:
        return "e.g. government structure charts, maps of Nigeria, symbols on Commons."
    if "history" in s:
        return "e.g. timelines, historical maps, portraits of figures when syllabus-relevant."
    if "literature" in s or "english" in s:
        return "e.g. author portrait or period/context image only if clearly relevant and on Commons."
    if "c.r.k" in s or "irk" in s or "islamic" in s or "religious" in s:
        return "e.g. clearly labelled religious/educational diagrams on Commons (respectful, syllabus-related)."
    return "e.g. any clear syllabus-related educational diagram or illustration found on Wikimedia Commons."
