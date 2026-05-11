"""Request/response schemas for `app.routers.credentials`."""
from __future__ import annotations

from typing import Optional

from noctusai_lib.api import StrictHttpModel


class CredentialsBody(StrictHttpModel):
    """PUT body — every provider key is optional; only non-null keys are written."""
    openai: Optional[str] = None
    anthropic: Optional[str] = None
    gemini: Optional[str] = None
