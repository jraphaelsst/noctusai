"""meta.diagnostics.* tools — adapter introspection + scope resolution.

Tools registered:
- meta.diagnostics.connection_status — adapter `.status()` introspection.
- meta.diagnostics.discover_scopes   — `resolve_oauth_scopes` wrapper.

Both PURE — no side-effect, no confirm gate.

`connection_status` wraps `MetaAdapter.status()` → `MetaConnectionStatus`
and surfaces `auth_mode` (`system_user` / `user_oauth` / `none`) — the
operator-visible signal for the silent-empty-data failure mode on
Business-Portfolio-owned assets (a query that "succeeds" with zero rows
because the wrong auth backend is active is otherwise invisible).

`discover_scopes` wraps the seed `resolve_oauth_scopes` (explicit list
verbatim → `discover_app_permissions` when app creds present → the
`META_KITCHEN_SINK_SCOPES` safety net). The seed function returns only
the resolved list; `source` is derived deterministically from the same
inputs the seed branches on (no scope logic re-implemented — the list
itself always comes from the seed call).

Verify-the-seed-ships-it: `get_meta_adapter`, `resolve_oauth_scopes`,
`META_KITCHEN_SINK_SCOPES`, `MetaGraphError` are all in
`noctusai_lib.integrations.meta.__all__` (read it). `MetaConnectionStatus`
is exported but consumed only via `.status()` here.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.meta import (
    META_KITCHEN_SINK_SCOPES,
    MetaGraphError,
    get_meta_adapter,
    resolve_oauth_scopes,
)

from ..settings import get_settings
from ..types import (
    ConnectionStatusInput,
    ConnectionStatusOutput,
    DiscoverScopesInput,
    DiscoverScopesOutput,
)

logger = logging.getLogger(__name__)


def _adapter():
    s = get_settings()
    return get_meta_adapter(
        system_user_token=s.meta_system_user_token,
        graph_version=None,
    )


# ─── Handlers ────────────────────────────────────────────────────────────


async def connection_status(args: dict) -> dict:
    ConnectionStatusInput(**args)
    adapter = _adapter()
    try:
        st = adapter.status()
    except MetaGraphError as e:
        env = typed_error(e)
        env["http_status"] = e.http_status
        env["is_auth_error"] = e.is_auth_error
        env["is_rate_limited"] = e.is_rate_limited
        return ConnectionStatusOutput(
            auth_mode=adapter.auth_mode, error=env
        ).model_dump()
    return ConnectionStatusOutput(
        configured=st.configured,
        adapter=st.adapter,
        auth_mode=st.auth_mode,
        consent_required=st.consent_required,
        user_id=st.user_id,
        user_name=st.user_name,
        pages_count=st.pages_count,
        instagram_accounts_count=st.instagram_accounts_count,
        status_error=st.error,
    ).model_dump()


async def discover_scopes(args: dict) -> dict:
    inp = DiscoverScopesInput(**args)
    s = get_settings()

    raw = (inp.configured_scopes or "").strip()
    explicit = bool(raw) and raw.lower() != "auto"

    scopes = resolve_oauth_scopes(
        configured=inp.configured_scopes,
        app_id=s.meta_app_id,
        app_secret=s.meta_app_secret,
    )

    # Source is derived from the same inputs the seed branches on — the
    # list itself always comes from the seed call (no re-implementation).
    if explicit:
        source = "explicit"
    elif scopes == list(META_KITCHEN_SINK_SCOPES):
        source = "kitchen_sink"
    else:
        source = "discovered"

    return DiscoverScopesOutput(scopes=scopes, source=source).model_dump()


# ─── Registration ───────────────────────────────────────────────────────


HANDLERS = {
    "meta.diagnostics.connection_status": connection_status,
    "meta.diagnostics.discover_scopes": discover_scopes,
}


def register(server: Server) -> dict:
    """Return this module's {tool_name: handler} map.

    The server aggregates these via `_kit.registry.build_registry`.
    """
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="meta.diagnostics.connection_status",
            description=(
                "Introspect the active Meta adapter. READ-ONLY. Surfaces "
                "`auth_mode` (system_user / user_oauth / none), "
                "`configured`, `adapter` (oauth/fake), counts, and any "
                "status error — the diagnostic for silent-empty-data on "
                "Business-Portfolio-owned assets."
            ),
            inputSchema=ConnectionStatusInput.model_json_schema(),
        ),
        Tool(
            name="meta.diagnostics.discover_scopes",
            description=(
                "Resolve the OAuth scope set the configured Meta app "
                "should request. READ-ONLY. `configured_scopes` explicit "
                "comma-list is used verbatim; 'auto'/empty triggers Graph "
                "app-permissions discovery, falling back to the kitchen-"
                "sink safety net. `source` reports which path was taken."
            ),
            inputSchema=DiscoverScopesInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
