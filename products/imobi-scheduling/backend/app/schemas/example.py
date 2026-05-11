"""
Example schemas — placeholder Pydantic models for the new product to fill in.

Pattern: one module per domain (``schemas/upload.py``, ``schemas/video.py``,
``schemas/dashboard.py``, …). Inputs end in ``Create`` / ``Update``,
outputs end in ``Out``. Keep request and response shapes separate — the
DB row schema is rarely the right wire shape.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field
from noctusai_lib.api import StrictHttpModel


class ExampleCreate(StrictHttpModel):
    """Request body for ``POST /api/example``.

    TODO(new-product): rename + extend with the real domain fields.
    """
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)


class ExampleOut(StrictHttpModel):
    """Response body for list / detail / create.

    TODO(new-product): rename + extend with the real domain fields.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    title: str
    description: str | None
    created_at: datetime


class ExampleListResponse(StrictHttpModel):
    """Cursor-paginated list response.

    Mirrors the shape used in production routers (e.g.
    ``videos_router``). ``next_cursor`` is opaque to the client —
    decoded server-side.
    """
    items: list[ExampleOut]
    next_cursor: str | None = None
