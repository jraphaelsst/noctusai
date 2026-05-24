"""Methodology wire schema — the synthesized course manual."""
from __future__ import annotations

from pydantic import BaseModel


class MethodologyResponse(BaseModel):
    available: bool
    markdown: str | None
    modules: list[str]
