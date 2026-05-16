"""`/api/meta/{status,scopes}` introspection seam.

A factory `make_meta_router(...)` returning a FastAPI `APIRouter` —
the canonical seed router-seam shape (consumer mounts it via the
product app factory's `standard_routers` / explicit include; nothing
is auto-registered here). Read-only introspection only:

- `GET /api/meta/status` — adapter introspection + a live probe
  (`/me` + page/IG counts) with `auth_mode` surfaced so the operator
  can immediately see which auth backend is active. The silent-empty-
  data failure mode (BM-owned assets invisible to user OAuth) is
  otherwise undiagnosable from logs.
- `GET /api/meta/scopes` — four-layer scope audit: configured (what
  we'll request), Graph-discovered (what the app is approved for),
  kitchen-sink fallback (in-code default), granted-to-user (post
  consent, when a token is resolvable). Lets the operator answer "did
  Meta give me everything I asked for?" without ssh.

OAuth start/callback endpoints are intentionally NOT here — they
belong with the generic `noctusai_lib.security.oauth.oauth_router`
(consumed as-is per the brief; this package does not duplicate the
OAuth dance). This seam is read-only diagnostics.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter

from noctusai_lib.integrations.meta import _meta_api
from noctusai_lib.integrations.meta._meta_api import (
    META_KITCHEN_SINK_SCOPES,
    MetaGraphError,
)
from noctusai_lib.integrations.meta.types import MetaAdapter


def make_meta_router(
    *,
    get_adapter: Callable[[str | None], MetaAdapter],
    app_id: str | None = None,
    app_secret: str | None = None,
    configured_scopes: str | None = "auto",
    graph_version: str = _meta_api.DEFAULT_GRAPH_VERSION,
    prefix: str = "/api/meta",
) -> APIRouter:
    """Build the Meta introspection router.

    `get_adapter(org_id)` is the consumer-supplied callable returning
    a `MetaAdapter` (typically `lambda org: get_meta_adapter(...)`).
    `app_id` / `app_secret` enable the Graph-discovered scope layer
    (they query `/{app-id}/permissions`); absent → that layer is
    `None` and the kitchen-sink is the effective fallback."""

    router = APIRouter(prefix=prefix, tags=["meta"])

    @router.get("/status")
    def meta_status(org_id: str | None = None) -> dict[str, Any]:
        adapter = get_adapter(org_id)
        st = adapter.status()
        return {
            "configured": st.configured,
            "adapter": st.adapter,
            "auth_mode": st.auth_mode,
            "consent_required": st.consent_required,
            "user_id": st.user_id,
            "user_name": st.user_name,
            "pages_count": st.pages_count,
            "instagram_accounts_count": st.instagram_accounts_count,
            "error": st.error,
        }

    @router.get("/scopes")
    def meta_scopes(org_id: str | None = None) -> dict[str, Any]:
        discovered: list[str] | None = None
        if app_id and app_secret:
            discovered = _meta_api.discover_app_permissions(
                app_id=app_id, app_secret=app_secret, version=graph_version
            )
        resolved = _meta_api.resolve_oauth_scopes(
            configured=configured_scopes,
            app_id=app_id,
            app_secret=app_secret,
            version=graph_version,
        )
        granted: list[str] | None = None
        adapter = get_adapter(org_id)
        # Best-effort post-consent ground truth via /me/permissions.
        token_fn = getattr(adapter, "_user_token", None)
        if callable(token_fn):
            try:
                body = _meta_api.graph_get(
                    "me/permissions",
                    access_token=token_fn(),
                    version=graph_version,
                )
                granted = [
                    r["permission"]
                    for r in (body.get("data") or [])
                    if isinstance(r, dict)
                    and r.get("permission")
                    and r.get("status") == "granted"
                ]
            except (MetaGraphError, Exception):  # noqa: BLE001
                granted = None
        coverage = None
        if granted is not None and resolved:
            want = {s for s in resolved if s != "public_profile"}
            have = set(granted)
            coverage = (
                round(100.0 * len(want & have) / len(want), 1) if want else 100.0
            )
        return {
            "configured": resolved,
            "discovered": discovered,
            "kitchen_sink_fallback": list(META_KITCHEN_SINK_SCOPES),
            "granted_to_user": granted,
            "coverage_pct": coverage,
        }

    return router


__all__ = ["make_meta_router"]
