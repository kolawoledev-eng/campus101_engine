from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    exam: str = Field(..., examples=["waec", "jamb"])
    year: int = Field(default=2025, ge=2000, le=2100)
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
    # Classroom target: ~23–29 cards per syllabus topic when generating a full set.
    min_subtopics: int = Field(default=25, ge=23, le=50)
    read_time_target_minutes: int = Field(default=3, ge=2, le=3)
    user_email: Optional[str] = Field(default=None)
    source_url: Optional[str] = Field(default=None)


class PastQuestionRow(BaseModel):
    """One row for bulk insert into past_questions (licensed past papers)."""

    exam: str
    year: int = Field(..., ge=2000, le=2100)
    subject: str
    difficulty: Literal["easy", "medium", "hard"]
    topic: str = Field(..., min_length=1, max_length=200)
    question_text: str = Field(..., min_length=1)
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str
    explanation: Optional[str] = None
    image_url: Optional[str] = Field(
        default=None,
        description="Optional HTTPS URL for a diagram or figure referenced in the stem.",
    )
    source_label: Optional[str] = None
    learning_outcomes: List[str] = Field(default_factory=list)
    syllabus_alignment: Optional[str] = None
    source_type: str = Field(default="past")
    tokens_used: Optional[int] = None
    api_cost: Optional[float] = None

    @field_validator("correct_answer")
    @classmethod
    def norm_answer(cls, v: str) -> str:
        u = v.strip().upper()
        if u not in ("A", "B", "C", "D"):
            raise ValueError("correct_answer must be A, B, C, or D")
        return u


class BulkPastQuestionsRequest(BaseModel):
    questions: List[PastQuestionRow] = Field(default_factory=list)


class EnsureBucketsRequest(BaseModel):
    exam: str
    year: int = Field(..., ge=2000, le=2100)
    subject: str
    target_per_difficulty: int = Field(default=100, ge=1, le=100)
    max_questions_to_generate: int = Field(default=500, ge=1, le=5000)
    topics: Optional[List[str]] = Field(
        default=None,
        description="If set, only these syllabus topic names (exact match)",
    )
    user_email: Optional[str] = None


