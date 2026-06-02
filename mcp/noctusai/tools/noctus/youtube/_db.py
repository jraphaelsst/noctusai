"""Shared Supabase client factory for ``noctus.youtube.*`` tools.

All YouTube MCP tools query Supabase directly using the service-role key
(bypassing RLS — appropriate here because the MCP toolkit runs as the
platform operator, not as an end-user session).  Every tool module imports
``get_yt_client()`` from here instead of repeating the connection logic.

Data-access decision
--------------------
The YouTube data lives in ``social_wiring`` schema on the noctusai Supabase
project.  The MCP toolkit already has ``SUPABASE_URL`` +
``SUPABASE_SERVICE_ROLE_KEY`` in ``BaseAppSettings`` (env/.env file shared
across the monorepo).  ``make_supabase_client`` (from
``noctusai_lib.integrations.database``) is the canonical factory — it takes
``url + anon_key + service_role_key + schema`` and returns a configured
``supabase.Client``.  Passing ``""`` as the anon_key and the service-role
key as the third arg means the client runs as service role.

The alternative (psycopg2 direct) would skip supabase-py's PostgREST JSON
layer; that is only needed for raw SQL.  PostgREST is sufficient for the
SELECT/filter queries these tools execute, and keeps the dep surface
identical to what the products use.

Environment requirements
------------------------
``SUPABASE_URL``               — e.g. ``https://<ref>.supabase.co``
``SUPABASE_SERVICE_ROLE_KEY``  — service-role JWT (never exposed to the FE)

If either is absent the client raises on first use; tools return a structured
``{"error": "not_configured", ...}`` to the caller rather than crashing.
"""
from __future__ import annotations

import logging

from noctusai_lib.integrations.database import make_supabase_client

from settings import get_settings

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"


def get_yt_client():
    """Return a service-role Supabase client scoped to the ``social_wiring`` schema.

    Builds from ``get_settings()`` on every call — intentionally NOT a
    module-level singleton (follows the FastAPI dep factory pattern: slot
    populated at request time, not at import).
    """
    s = get_settings()
    if not s.supabase_url or not s.supabase_service_role_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set for noctus.youtube.* tools"
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
            "Add them to .env or the MCP server environment to enable YouTube tools."
        ),
    }
