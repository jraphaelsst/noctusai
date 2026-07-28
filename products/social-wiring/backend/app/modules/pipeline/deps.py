"""DI seam: this product's auth shape mapped to the seed's `PipelineContext`.

`get_current_user_org_unified` yields `(user, token, raw_org)` and the module
talks to a schema-scoped ADMIN client (RLS as defense-in-depth, org filtering
explicit in every query) — the same shape the Leads module uses, and a
different shape from erp's `(user, token)` + RLS-scoped user client.

Mapping both onto one context triple is why the seed factory takes
`resolve_context` instead of `get_current_user` + `get_user_client`: the first
version of that signature was erp's shape by coincidence, and this product
could not have adopted it without contorting its own auth
(`KB § PATTERNS/architect/seed-canonical-defaults.md`).
"""
from __future__ import annotations

import weakref
from typing import Any

from noctusai_lib.domain.pipeline import PipelineContext

from app.dependencies import coerce_org_uuid, get_admin_client

_SCHEMA = "social_wiring"
_scoped_cache: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def get_pipeline_client() -> Any:
    """The `social_wiring`-scoped admin client, bound once per admin object.

    Same caching rationale as `app/modules/leads/deps.py`: `MockSupabaseClient
    .schema()` returns a fresh wrapper with an EMPTY row cache on every call,
    so re-binding per query silently loses writes between requests in tests.
    """
    admin = get_admin_client()
    cached = _scoped_cache.get(admin)
    if cached is None:
        cached = admin.schema(_SCHEMA)
        _scoped_cache[admin] = cached
    return cached


def pipeline_context(auth: tuple) -> PipelineContext:
    """Map `(user, token, raw_org)` → the seed's context triple."""
    user, _token, raw_org = auth
    return PipelineContext(
        db=get_pipeline_client(),
        org_id=str(coerce_org_uuid(raw_org)),
        user_id=getattr(user, "id", None),
    )


__all__ = ["get_pipeline_client", "pipeline_context"]
