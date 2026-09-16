"""Shared Supabase client factory for ``noctus.photo_editing.*`` tools.

Every tool queries Supabase directly using the service-role key
(bypassing RLS — appropriate here because the MCP toolkit runs as the
platform operator, not as an end-user session). Every tool module imports
``get_pe_client()`` from here instead of repeating the connection logic.
Mirrors ``tools.noctus.youtube._db`` (this umbrella's template).

Data-access decision
---------------------
The photo-editing pipeline tables (``fotos_*``) live in the
``social_wiring`` schema on the noctusai Supabase project — the default
schema this client is scoped to. ``public.organizations`` (org
resolution) is reached via ``client.schema("public")`` per call, the same
cross-schema pattern ``SupabasePhotoEditingRepository._t()`` uses for
``cost_ledger`` (Core, ``public`` schema) from a ``social_wiring``-scoped
client — one client, ``.schema(...)`` overrides the default per query.

Environment requirements
-------------------------
``SUPABASE_URL``               — e.g. ``https://<ref>.supabase.co``
``SUPABASE_SERVICE_ROLE_KEY``  — service-role JWT (never exposed to the FE)

If either is absent the client raises on first use; tools return a
structured ``{"error": "not_configured", ...}`` to the caller rather than
crashing.
"""
from __future__ import annotations

import logging

from noctusai_lib.integrations.database import make_supabase_client

from settings import get_settings

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"

#: Private bucket for per-org uploaded + edited photos (plan §4, migration
#: 127_fotos_storage_buckets.sql). Path shape ``{org_id}/{lote_id}/{foto_id}/...``.
BUCKET = "edicao-fotos"

#: Signed-URL lifetime — capped at 1h per the brief (short-lived by design;
#: never a long-lived pointer into a private bucket).
SIGNED_URL_TTL_SECONDS = 3600


def get_pe_client():
    """Return a service-role Supabase client scoped to the ``social_wiring`` schema.

    Builds from ``get_settings()`` on every call — intentionally NOT a
    module-level singleton (follows the FastAPI dep factory pattern: slot
    populated at request time, not at import).
    """
    s = get_settings()
    if not s.supabase_url or not s.supabase_service_role_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set for "
            "noctus.photo_editing.* tools"
        )
    return make_supabase_client(
        url=s.supabase_url,
        anon_key="",
        service_role_key=s.supabase_service_role_key,
        schema=_SCHEMA,
    )


def _not_configured_error(tool: str) -> dict:
    """Structured error for missing Supabase credentials."""
    return {
        "error": "not_configured",
        "tool": tool,
        "message": (
            "SUPABASE_URL and/or SUPABASE_SERVICE_ROLE_KEY are not set. "
            "Add them to .env or the MCP server environment to enable "
            "noctus.photo_editing.* tools."
        ),
    }
