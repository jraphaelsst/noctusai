"""DI seam: the ``social_wiring``-scoped admin client, cached by the
underlying admin-client OBJECT (not re-bound on every call).

Why this exists
────────────────
``client.schema(name)`` on ``noctusai_lib.testing.MockSupabaseClient``
returns a BRAND NEW wrapper with an EMPTY per-table row cache every
single time it's called (confirmed empirically while building this
module's test suite) — so a service pattern of ``client.schema(SCHEMA)
.table(t)`` called fresh on every read/write (the shape used elsewhere
in this product, e.g. ``app/services/clients_service.py``,
``app/modules/mailchimp/store.py``) silently loses every prior
insert/update the instant two SEPARATE calls re-resolve the schema
binding — which is exactly what happens across two separate HTTP
requests in a test (POST then GET). Those other call sites don't hit
this because their OWN tests back the service with the SQLite dev
client instead (``SQLiteClient.schema()`` returns ``self`` — an
identity no-op, no fresh-wrapper problem). This module's services need
``MockSupabaseClient``'s richer filter surface (``gte``/``lte``/
``ilike`` — see ``services/query.py``'s docstring), so the fix is here
instead: bind the schema ONCE per underlying admin-client object and
reuse that SAME bound object for every subsequent call.

A real Supabase client doesn't have the data-loss problem (``.schema()``
is stateless HTTP-request shaping), but re-binding it on every query is
still wasted work — the cache benefits both environments.

The cache is a ``WeakKeyDictionary`` keyed by the admin-client object
itself (not ``id()``) so a test's ``MockSupabaseClient`` is never kept
alive past its fixture teardown by this module-level cache.
"""
from __future__ import annotations

import weakref
from typing import Any

from app.dependencies import get_admin_client

_SCHEMA = "social_wiring"
_scoped_cache: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def get_leads_client() -> Any:
    """FastAPI dependency — the ``social_wiring``-scoped admin client."""
    admin = get_admin_client()
    cached = _scoped_cache.get(admin)
    if cached is None:
        cached = admin.schema(_SCHEMA)
        _scoped_cache[admin] = cached
    return cached


__all__ = ["get_leads_client"]
