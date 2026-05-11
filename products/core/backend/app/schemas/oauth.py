"""Request/response schemas for `app.routers.oauth`."""
from __future__ import annotations

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class OAuthCallbackBody(StrictHttpModel):
    """Body for the OAuth callback — used to pass info for profile creation."""
    provider: str = Field(..., description="OAuth provider (google, azure)")
