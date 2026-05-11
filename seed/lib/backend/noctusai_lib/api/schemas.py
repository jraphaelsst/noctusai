"""HTTP-boundary base schemas — strict-by-default request/response shapes.

The Pydantic v2 default of `extra="ignore"` silently drops unknown keys.
Frontend hooks typed `mutationFn<Record<string, unknown>>` + backend schemas
relying on that default = silent data-loss when a hook misroutes (2026-05-11
therapy clinic-settings bug — memory `feedback_pydantic_silent_drop_kills_writes`).

`StrictHttpModel` rejects unknown keys with `ValidationError` → FastAPI converts
to **422 Unprocessable Entity** with a body that names the offending `loc`.
The misroute becomes immediately diagnosable instead of silently swallowed.

Usage
-----

>>> from noctusai_lib.api import StrictHttpModel
>>>
>>> class SettingsUpdate(StrictHttpModel):
...     name: str | None = None
...     phone: str | None = None
...
>>> # FastAPI route receiving SettingsUpdate now 422s on any unknown key.

Pydantic v2 **merges** `ConfigDict` across the MRO, so a subclass that adds
its own `model_config` keeps the parent's `extra="forbid"` automatically:

>>> from pydantic import ConfigDict
>>>
>>> class WithOrm(StrictHttpModel):
...     model_config = ConfigDict(from_attributes=True)
...
>>> # WithOrm.model_config == {"extra": "forbid", "from_attributes": True}

To deliberately opt OUT of strictness (e.g. accept unknown DB columns), the
subclass must explicitly re-declare `extra="allow"` (or `"ignore"`):

>>> class Loose(StrictHttpModel):
...     model_config = ConfigDict(extra="allow")  # explicit opt-out

Carve-out (`extra="allow"`) is a deliberate, documented opt-out — see
`products/adconnect/backend/app/schemas/admin.py::DistributorWithMetricsOut`
for the canonical "accept unknown DB columns" pattern.

See `KB § PATTERNS/pydantic-strict-http.md` for migration guidance.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictHttpModel(BaseModel):
    """Pydantic base for HTTP-boundary schemas. Rejects unknown keys (422).

    Inherit from this instead of `pydantic.BaseModel` for any schema that:
    - is the request body of a FastAPI route, OR
    - is the response model of a FastAPI route AND the response is consumed
      by typed frontend code (the schema acts as a contract in both directions).

    Subclasses MAY add `model_config = ConfigDict(...)` and keep strictness
    automatically — Pydantic v2 merges the child config with the parent's, so
    `extra="forbid"` propagates unless the subclass deliberately overrides it
    with `extra="allow"` / `extra="ignore"` (see module docstring).
    """

    model_config = ConfigDict(extra="forbid")
