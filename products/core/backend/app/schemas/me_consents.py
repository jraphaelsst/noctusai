"""Request/response schemas for `app.routers.me_consents`."""
from __future__ import annotations

from noctusai_lib.api import StrictHttpModel


class ConsentToggle(StrictHttpModel):
    granted: bool
