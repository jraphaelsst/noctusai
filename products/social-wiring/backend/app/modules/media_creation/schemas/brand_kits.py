"""Brand-kit schemas — persona + design system text blobs."""
from __future__ import annotations

from typing import Optional

from noctusai_lib.api import StrictHttpModel


class BrandKitCreate(StrictHttpModel):
    name: str
    persona: str = ""
    design_system: str = ""
    default_lang: str = "pt-BR"


class BrandKitUpdate(StrictHttpModel):
    name: Optional[str] = None
    persona: Optional[str] = None
    design_system: Optional[str] = None
    default_lang: Optional[str] = None
