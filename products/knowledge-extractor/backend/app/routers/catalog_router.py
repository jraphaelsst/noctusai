"""Catalog router — browse the extracted transcripts/summaries (filesystem reads).

Auth-gated (logged-in users). ``get_data_dir`` is a DI seam tests override to a
temp dir. Explicit ``status_code`` on each endpoint so the status-assertion keeper
has something to pin.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user_org, get_data_dir
from app.schemas.catalog import (
    CatalogResponse,
    CatalogTotals,
    LessonContentResponse,
    LessonSummary,
    ModuleLessonsResponse,
    ModuleSummary,
)
from app.services.catalog_service import CatalogService

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("", response_model=CatalogResponse)
async def get_catalog(
    auth: tuple = Depends(get_current_user_org),
    data_dir: Path = Depends(get_data_dir),
) -> CatalogResponse:
    """Overview: every module with lesson / transcript / summary counts + totals."""
    modules = CatalogService(data_dir).list_modules()
    return CatalogResponse(
        modules=[
            ModuleSummary(name=m.name, lessons=m.lessons, transcripts=m.transcripts, summaries=m.summaries)
            for m in modules
        ],
        totals=CatalogTotals(
            modules=len(modules),
            lessons=sum(m.lessons for m in modules),
            transcripts=sum(m.transcripts for m in modules),
            summaries=sum(m.summaries for m in modules),
        ),
    )


@router.get("/modules/{module}", response_model=ModuleLessonsResponse)
async def get_module_lessons(
    module: str,
    auth: tuple = Depends(get_current_user_org),
    data_dir: Path = Depends(get_data_dir),
) -> ModuleLessonsResponse:
    """Lessons of one module (transcript/summary presence + char counts)."""
    lessons = CatalogService(data_dir).module_lessons(module)
    if lessons is None:
        raise HTTPException(status_code=404, detail=f"módulo não encontrado: {module}")
    return ModuleLessonsResponse(
        module=module,
        lessons=[
            LessonSummary(
                lesson=row.lesson,
                has_transcript=row.has_transcript,
                has_summary=row.has_summary,
                transcript_chars=row.transcript_chars,
                summary_chars=row.summary_chars,
            )
            for row in lessons
        ],
    )


@router.get("/lessons/{module}/{lesson}", response_model=LessonContentResponse)
async def get_lesson_content(
    module: str,
    lesson: str,
    auth: tuple = Depends(get_current_user_org),
    data_dir: Path = Depends(get_data_dir),
) -> LessonContentResponse:
    """The transcript + summary markdown for one lesson."""
    content = CatalogService(data_dir).lesson_content(module, lesson)
    if content is None:
        raise HTTPException(status_code=404, detail=f"aula não encontrada: {module}/{lesson}")
    transcript, summary = content
    return LessonContentResponse(module=module, lesson=lesson, transcript=transcript, summary=summary)
