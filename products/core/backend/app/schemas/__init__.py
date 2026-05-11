"""HTTP-boundary request/response schemas for products/core.

Mirrors `products/personal-finance/backend/app/schemas/`: per-router module
files (`app/schemas/<router_name>.py`), each holding the Pydantic schemas
that previously lived inline in `app/routers/<router_name>.py`.

All schemas inherit from `noctusai_lib.api.StrictHttpModel` so unknown
keys produce **422 Unprocessable Entity** instead of being silently dropped
(memory `feedback_pydantic_silent_drop_kills_writes`; KB §
PATTERNS/pydantic-strict-http.md).

The package is intentionally `__init__.py`-only — consumers import the
concrete classes from the submodule (`from app.schemas.plans import
PlanCreate, PlanUpdate`), matching the PF convention.
"""
