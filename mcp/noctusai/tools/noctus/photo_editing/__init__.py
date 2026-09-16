"""``noctus.photo_editing.*`` tool umbrella — Edição de Fotos read tools.

Sub-tools
---------
  ``noctus.photo_editing.list_rejections``
      Per-rejected-photo detail for an org (optionally scoped to one
      batch / a set of edit types): the reviewer's comment, the effective
      style-guide version in force at submit time, the editor model that
      produced the ``depois`` (after) image, and short-lived signed
      before/after URLs (TTL ≤ 1h). Lets Claude Code inspect rejected
      photos directly (plan §1: "Claude Code must be able to inspect
      rejected photos through an MCP tool").

Data-access path
-----------------
Queries Supabase directly via ``noctusai_lib.integrations.database.
make_supabase_client`` (service-role, ``social_wiring`` schema default,
``public`` schema for ``organizations``) — same dual-use, direct-query
shape as ``noctus.youtube.*`` (this umbrella's template). Credentials come
from ``BaseAppSettings.supabase_url`` + ``supabase_service_role_key``.

Org resolution
--------------
Every tool accepts an ``org`` parameter resolved by
``_resolve.resolve_org``:
  - UUID string      → matches ``public.organizations.id``
  - name/slug string → case-insensitive ilike on ``nome`` or exact ``slug``
  - empty / None      → ``error: org_required`` (many orgs exist; there is
    no single-org auto-select the way YouTube has one channel per session)
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every ``noctus.photo_editing.*`` tool on the given FastMCP server."""
    from . import list_rejections

    list_rejections.register(server)


__all__ = ["register_all"]
