"""Brand-reference schemas — uploaded brand assets (URLs only in v1)."""
from __future__ import annotations

from typing import Literal, Optional

from noctusai_lib.api import StrictHttpModel

ReferenceKind = Literal["model", "prompt", "palette", "typography"]


class ReferenceCreate(StrictHttpModel):
    kind: ReferenceKind
    label: str
    asset_url: Optional[str] = None
    notes: Optional[str] = None
