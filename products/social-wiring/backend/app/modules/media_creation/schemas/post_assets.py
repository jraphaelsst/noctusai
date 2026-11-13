"""Schemas for ``cs_post_assets`` (CoreStudio post axes, migration 342)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

AssetStatus = Literal["em_producao", "pronto", "aprovado", "reprovado", "arquivado"]


class AssetRegistrar(StrictHttpModel):
    """Register an uploaded file as an asset of the post.

    Nothing about the file is typed by the caller: the backend reads the media type, size, aspect ratio and
    duration from the stored bytes. ``ordem`` omitted = append at the end; an existing ``ordem`` = a NEW version
    of that position.
    """

    storage_path: str = Field(min_length=1, max_length=1024)
    ordem: Optional[int] = Field(default=None, ge=1, le=50)


class AssetStatusUpdate(StrictHttpModel):
    status: AssetStatus
