"""Pydantic models for OAuth refresh-token persistence (e.g. Google Calendar).

The ``refresh_token`` field is sensitive — products MUST encrypt before
INSERT (application-level contract; not enforced by DB). The schema marks
it Field-level for downstream LGPD redaction tooling.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, Field
from noctusai_lib.api import StrictHttpModel


class OAuthCredentialCreate(StrictHttpModel):
    provider: str = Field(..., min_length=1, max_length=40)
    account_email: str = Field(..., min_length=1, max_length=255)
    # Encrypted at-rest by the application layer before INSERT.
    refresh_token: str = Field(..., min_length=1)
    access_token: str | None = None
    access_token_expires_at: datetime | None = None
    scopes: str = Field(..., min_length=1)


class OAuthCredentialUpdate(StrictHttpModel):
    refresh_token: str | None = Field(None, min_length=1)
    access_token: str | None = None
    access_token_expires_at: datetime | None = None
    scopes: str | None = None


class OAuthCredentialOut(StrictHttpModel):
    """Response shape — refresh_token redacted at the API boundary.

    Routers SHOULD strip ``refresh_token`` from any list/detail response;
    storing it here typed-but-clearly-sensitive keeps the contract
    explicit. Use ``model_dump(exclude={"refresh_token"})`` at the wire.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    provider: str
    account_email: str
    refresh_token: str  # Sensitive — see class docstring.
    access_token: str | None
    access_token_expires_at: datetime | None
    scopes: str
    created_at: datetime
    updated_at: datetime
