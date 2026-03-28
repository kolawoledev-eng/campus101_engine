from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SchoolQuestionGenerateRequest(BaseModel):
    exam_mode: str = Field(..., examples=["post-utme", "jupeb"])
    institution_name: str = Field(..., examples=["University of Lagos"])
    year: int = Field(..., ge=2000, le=2100)
    subject: str = Field(..., examples=["Physics", "English"])
    topic: str = Field(default="all topics")
    difficulty: str = Field(default="medium", examples=["easy", "medium", "hard"])
    count: int = Field(default=20, ge=1, le=100)
    user_email: Optional[str] = Field(default=None)

