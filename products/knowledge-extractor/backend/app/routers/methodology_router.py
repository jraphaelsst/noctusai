"""Methodology router — the synthesized course manual (filesystem read).

``data/METHODOLOGY.md`` is the unified manual; ``data/methodology/<module>.md``
are the per-module syntheses. Auth-gated; ``get_data_dir`` is a DI seam.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user_org, get_data_dir
from app.schemas.methodology import MethodologyResponse

router = APIRouter(prefix="/api/methodology", tags=["methodology"])


@router.get("", response_model=MethodologyResponse)
async def get_methodology(
    auth: tuple = Depends(get_current_user_org),
    data_dir: Path = Depends(get_data_dir),
) -> MethodologyResponse:
    manual = data_dir / "METHODOLOGY.md"
    methodology_dir = data_dir / "methodology"
    modules = (
        sorted(p.stem for p in methodology_dir.glob("*.md") if p.is_file())
        if methodology_dir.is_dir()
        else []
    )
    markdown = manual.read_text(encoding="utf-8") if manual.is_file() else None
    return MethodologyResponse(
        available=markdown is not None or bool(modules),
        markdown=markdown,
        modules=modules,
    )
