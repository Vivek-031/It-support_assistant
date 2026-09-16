import re
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

MIN_QUESTION_LENGTH = 10
MAX_QUESTION_LENGTH = 1000


class TicketCreate(BaseModel):
    question: str = Field(..., min_length=MIN_QUESTION_LENGTH, max_length=MAX_QUESTION_LENGTH)

    @field_validator("question")
    @classmethod
    def clean_question(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < MIN_QUESTION_LENGTH:
            raise ValueError(f"Question must be at least {MIN_QUESTION_LENGTH} characters.")
        if not re.search(r"[A-Za-z]{2,}", value):
            raise ValueError("Question must describe the problem in words.")
        return value


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TimestampedModel(ORMModel):
    created_at: datetime

    # SQLite drops tzinfo; values are stored in UTC, so re-attach it for correct client display.
    @field_validator("created_at")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class SourceOut(BaseModel):
    id: int
    title: str
    category: str
    score: float


class TicketSummary(TimestampedModel):
    id: int
    question: str
    status: str


class TicketOut(TimestampedModel):
    id: int
    question: str
    status: str
    retrieved_context: str | None
    sources: list[SourceOut]
    ai_response: str | None
    llm_provider: str | None
    error_message: str | None


class KBArticleOut(ORMModel):
    id: int
    title: str
    category: str
    keywords: str
    problem: str
    solution: str


class KBSearchResult(BaseModel):
    id: int
    title: str
    category: str
    score: float
    solution: str
