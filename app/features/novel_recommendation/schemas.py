from pydantic import BaseModel, Field


class NovelRecommendationRequest(BaseModel):
    exam: str = Field(..., examples=["jamb", "waec"])
    subject: str = Field(..., examples=["Literature in English"])
    count: int = Field(default=5, ge=1, le=20)

