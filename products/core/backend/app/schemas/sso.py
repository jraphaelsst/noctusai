"""Request/response schemas for `app.routers.sso`.

Note: this router has the only `response_model=` in core (`SSOSessionResponse`
on POST /api/sso/session). `StrictHttpModel` applies to both request AND
response — request side gets 422-on-unknown-key (silent-drop defense);
response side gets the same contract direction (typed FE consumers).
"""
from __future__ import annotations

from noctusai_lib.api import StrictHttpModel


class SSOTokenRequest(StrictHttpModel):
    product_slug: str


class SSOValidateRequest(StrictHttpModel):
    token: str


class SSOSessionRequest(StrictHttpModel):
    token: str


class SSOSessionResponse(StrictHttpModel):
    access_token: str
    refresh_token: str
    user_id: str
    email: str
