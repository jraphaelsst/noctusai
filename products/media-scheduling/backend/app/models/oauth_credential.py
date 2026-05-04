"""`media_scheduling.oauth_credentials` row shape.

Phase 4's `OAuthCredentialResolver` reads these rows + writes refreshed
access tokens back. Phase 3's `routers/oauth.py` (Engineer C) writes the
initial token-exchange row.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OAuthCredential(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    account_email: str
    refresh_token: str
    access_token: str | None = None
    access_token_expires_at: datetime | None = None
    scopes: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
