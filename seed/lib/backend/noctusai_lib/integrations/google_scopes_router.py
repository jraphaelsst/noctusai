"""`google_scopes_router(...)` — the 4-layer `/api/google/scopes`
introspection seam.

Reconciled 2026-05-16 by `projects/social-wiring-absorption/` Wave 1.E3
from the workspace's `app/routers/google_router.py`
(`reference/.promotions/google-scope-discovery.md`).

WHY a factory router (mirrors `noctusai_lib.security.oauth.oauth_router`)
------------------------------------------------------------------------
The endpoint reads two product-specific things: (a) the product's
configured `GOOGLE_OAUTH_SCOPES` env value + its kitchen-sink list,
and (b) the granted scopes for a tenant (requires the product's
stored access token). Neither is knowable seed-side, so the product
injects both via callables — the router stays unopinionated about
config source + credential storage, exactly like `oauth_router`'s
`on_callback` seam.

The prefix is `/api/google/` (NOT `/api/calendar/`) deliberately:
Google scopes span Calendar + Drive today and Gmail/Sheets/Docs
tomorrow — this is Google-wide introspection, not Calendar-specific.

4-layer response
----------------
    {
      "configured":         [<what oauth_start would request>],
      "kitchen_sink":       [<the in-code full default list>],
      "granted_to_user":    [<from tokeninfo post-consent>] | null,
      "declined_by_user":   [<configured - granted>]        | null,
      "coverage_pct":       100.0 | null,
      "note":               "<actionable operator text>"
    }

`granted_to_user` / `declined_by_user` / `coverage_pct` are `null`
when no access token is resolvable (consent not yet completed) — the
operator reads that as "configured looks right, now run consent".
"""

from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import APIRouter, Query

from noctusai_lib.integrations.google_scopes import (
    GOOGLE_KITCHEN_SINK_SCOPES,
    diagnose_consent_screen_gaps,
    discover_granted_scopes,
    resolve_google_scopes,
)

# Product injects: given an optional tenant id, return that tenant's
# current Google access token, or None if consent hasn't completed.
# Async so products can hit their DB / vault without blocking.
AccessTokenResolver = Callable[[str | None], Awaitable[str | None]]

# Product injects: return the raw configured scope env value (e.g.
# settings.google_oauth_scopes). Sync — it's a config read.
ConfiguredScopesProvider = Callable[[], str | None]


def google_scopes_router(
    *,
    configured_scopes: ConfiguredScopesProvider,
    access_token_resolver: AccessTokenResolver | None = None,
    kitchen_sink: list[str] | None = None,
    prefix: str = "/api/google",
) -> APIRouter:
    """Build the `/api/google/scopes` introspection router.

    Args:
        configured_scopes: returns the product's raw `GOOGLE_OAUTH_SCOPES`
            env value (`"auto"`, empty, or an explicit list string).
        access_token_resolver: optional async callable returning a
            tenant's stored Google access token (for the post-consent
            tokeninfo probe). When None, the granted-layer is always
            `null` (introspection still works for the configured /
            kitchen-sink layers — useful before consent).
        kitchen_sink: per-product scope list override; defaults to
            `GOOGLE_KITCHEN_SINK_SCOPES`.
        prefix: mount prefix. Default `/api/google` (Google-wide, not
            Calendar-specific — scopes span Calendar/Drive/Gmail/...).

    Returns:
        A FastAPI `APIRouter` exposing `GET {prefix}/scopes`.
    """
    sink = kitchen_sink if kitchen_sink is not None else GOOGLE_KITCHEN_SINK_SCOPES
    router = APIRouter(prefix=prefix, tags=["google-scopes"])

    @router.get("/scopes")
    async def get_google_scopes(  # noqa: D401 — endpoint
        tenant_id: str | None = Query(
            default=None,
            description="Tenant whose granted scopes to probe (optional).",
        ),
    ) -> dict:
        configured = resolve_google_scopes(
            configured_scopes(), kitchen_sink=sink
        )
        result: dict = {
            "configured": configured,
            "kitchen_sink": list(sink),
            "granted_to_user": None,
            "declined_by_user": None,
            "coverage_pct": None,
            "note": (
                "Consent not yet probed. Run the OAuth consent flow, then "
                "re-query with ?tenant_id= to see granted vs configured. "
                "Every configured scope must also be added in GCP Console "
                "→ OAuth Consent Screen → Scopes (Google blocks "
                "unconfigured scopes)."
            ),
        }
        if access_token_resolver is None:
            return result
        access_token = await access_token_resolver(tenant_id)
        if not access_token:
            return result
        granted = discover_granted_scopes(access_token)
        if not granted:
            result["note"] = (
                "Token resolved but tokeninfo returned no scopes "
                "(token expired/revoked, or network error — see logs). "
                "Treat granted as unknown."
            )
            return result
        gaps = diagnose_consent_screen_gaps(configured, granted)
        result["granted_to_user"] = gaps["granted"]
        result["declined_by_user"] = gaps["missing"]
        result["coverage_pct"] = gaps["coverage_pct"]
        result["note"] = (
            "coverage_pct=100 → GCP Console accepted every configured "
            "scope. <100 → the listed declined_by_user scopes are "
            "missing from the GCP Console Consent Screen config; add "
            "them there and re-consent."
        )
        return result

    return router


__all__ = ["google_scopes_router", "AccessTokenResolver", "ConfiguredScopesProvider"]
