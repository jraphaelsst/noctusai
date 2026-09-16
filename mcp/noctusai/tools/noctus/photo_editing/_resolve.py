"""Org resolution helper for ``noctus.photo_editing.*`` tools.

Every tool accepts an ``org`` parameter that can be:
  - a UUID string           → matched against ``public.organizations.id``
  - a name/slug string      → exact match on ``slug``, else case-insensitive
                               prefix match on ``nome`` (first match wins)
  - empty string / ``None`` → ``{"error": "org_required"}`` — the platform
    has many orgs (unlike YouTube's one-channel-per-session shape in the
    sibling ``_resolve.resolve_account``), so there is no sensible
    auto-select default.

If resolution fails the tool returns a dict with
``"error": "org_not_found"`` rather than raising, so the agent can surface
the issue gracefully.
"""
from __future__ import annotations

import logging
import uuid as _uuid_mod
from typing import Any

logger = logging.getLogger(__name__)

_ORG_REQUIRED: dict = {
    "error": "org_required",
    "message": "org is required — pass an organization UUID, slug, or name.",
}


def _is_uuid(s: str) -> bool:
    try:
        _uuid_mod.UUID(s)
        return True
    except ValueError:
        return False


def resolve_org(client, org: str | None) -> dict | None:
    """Return the ``public.organizations`` row for the given ``org`` specifier.

    Parameters
    ----------
    client:
        Supabase client (service-role). Queries ``public.organizations``
        via ``client.schema("public")`` regardless of the client's own
        default schema.
    org:
        UUID, slug, name substring, or empty/None.

    Returns
    -------
    dict | None
        The matching ``{id, nome, slug}`` row, ``{"error": "org_required"}``
        when ``org`` is empty, or ``None`` when no row matches.
    """
    if not org:
        logger.warning("resolve_org: called with no org specifier")
        return dict(_ORG_REQUIRED)

    if _is_uuid(org):
        resp = (
            client.schema("public")
            .from_("organizations")
            .select("id, nome, slug")
            .eq("id", org)
            .limit(1)
            .execute()
        )
        rows: list[dict[str, Any]] = resp.data or []
        return rows[0] if rows else None

    # Exact slug match first (slugs are unique + the canonical machine key).
    resp = (
        client.schema("public")
        .from_("organizations")
        .select("id, nome, slug")
        .eq("slug", org)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if rows:
        return rows[0]

    # Fall back to a case-insensitive prefix match on the display name.
    resp = (
        client.schema("public")
        .from_("organizations")
        .select("id, nome, slug")
        .ilike("nome", f"%{org}%")
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if rows:
        return rows[0]

    logger.warning("resolve_org: no organization matched specifier=%r", org)
    return None
