"""Catalog wire schemas — browse the extracted transcripts/summaries."""
from __future__ import annotations

from pydantic import BaseModel


class ModuleSummary(BaseModel):
    name: str
    lessons: int
    transcripts: int
    summaries: int


class CatalogTotals(BaseModel):
    modules: int
    lessons: int
    transcripts: int
    summaries: int


class CatalogResponse(BaseModel):
    modules: list[ModuleSummary]
    totals: CatalogTotals


class LessonSummary(BaseModel):
    lesson: str
    has_transcript: bool
    has_summary: bool
    transcript_chars: int
    summary_chars: int


class ModuleLessonsResponse(BaseModel):
    module: str
    lessons: list[LessonSummary]


class LessonContentResponse(BaseModel):
    module: str
    lesson: str
    transcript: str | None
    summary: str | None
