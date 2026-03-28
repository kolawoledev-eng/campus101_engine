from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    exam: str = Field(..., examples=["waec", "jamb"])
    year: int = Field(..., ge=2000, le=2100)
    subject: str = Field(..., examples=["Physics", "Mathematics"])
    difficulty: str = Field(..., examples=["easy", "medium", "hard"])
    topic: str = Field(default="all topics")
    count: int = Field(default=40, ge=1, le=100)
    user_email: Optional[str] = Field(default=None)


class TopicIngestionRequest(BaseModel):
    exam: str = Field(..., examples=["waec", "jamb"])
    year: int = Field(..., ge=2000, le=2100)
    subject: str = Field(..., examples=["Physics", "Mathematics"])
    raw_topics: list[str] = Field(default_factory=list, description="Raw topic names from scraping/manual input")
    source_text: Optional[str] = Field(
        default=None,
        description="Optional unstructured syllabus text for Claude to extract/normalize topics from",
    )
    source_url: Optional[str] = Field(default=None, description="Optional reference URL for audit trail")
    create_subject_if_missing: bool = Field(
        default=False,
        description="If true, create subject under exam when it does not exist",
    )


class StudyNotesGenerateRequest(BaseModel):
    exam: str = Field(..., examples=["jamb", "waec"])
    year: int = Field(..., ge=2000, le=2100)
    subject: str = Field(..., examples=["Physics", "Use of English", "History"])
    topic: str = Field(..., examples=["Kinematics", "Comprehension"])
    min_subtopics: int = Field(default=20, ge=20, le=50)
    read_time_target_minutes: int = Field(default=3, ge=2, le=3)
    user_email: Optional[str] = Field(default=None)
    source_url: Optional[str] = Field(default=None)


