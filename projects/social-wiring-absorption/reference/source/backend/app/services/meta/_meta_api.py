"""Shared HTTP plumbing for Meta Graph API calls.

A thin wrapper around ``httpx.Client`` that handles:

* Picking the Graph API version from settings (``META_GRAPH_API_VERSION``).
* Attaching ``access_token`` to every call as a querystring parameter.
* Parsing Graph's error envelope (``{"error": {"message": ..., "type": ..., "code": ...}}``)
  into a typed ``MetaGraphError`` so callers can distinguish auth failures
  from rate limits from "real" errors.
* Following ``paging.next`` cursors when the caller asks for more results
  than fit in a single page.

We don't pull facebook-sdk or any other SDK because:

1. The Graph API is a thin REST surface — wrapping httpx is cheaper than
   maintaining a vendor dep.
2. We need full control over the user/page token chain (different tokens
   for different endpoints) which most SDKs hide behind a Session shape.
"""
from __future__ import annotations

import logging
from typing import Any, Iterator

import httpx

from app.config import settings as default_settings

logger = logging.getLogger(__name__)


GRAPH_BASE = "https://graph.facebook.com"


class MetaGraphError(Exception):
    """Graph API returned an error envelope.

    Carries the ``code`` and ``type`` so callers can branch on
    ``OAuthException`` (token expired / scopes missing) vs.
    ``GraphMethodException`` (endpoint misuse) vs. rate-limit codes 4 / 17 / 32.
    """

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        sub_code: int | None = None,
        type_: str | None = None,
        http_status: int | None = None,
        fbtrace_id: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.sub_code = sub_code
        self.type = type_
        self.http_status = http_status
        self.fbtrace_id = fbtrace_id

    @property
    def is_auth_error(self) -> bool:
        # 190 = invalid OAuth token; 102 = session expired; 467 = invalid
        # access token for the user.
        return self.code in {102, 190, 467}

    @property
    def is_rate_limited(self) -> bool:
        # Application rate limit, user rate limit, page-level rate limit.
        return self.code in {4, 17, 32, 613}


def _api_version(settings=None) -> str:
    settings = settings or default_settings
    return getattr(settings, "meta_graph_api_version", "v21.0")


def _base_url(*, settings=None) -> str:
    return f"{GRAPH_BASE}/{_api_version(settings)}"


def _raise_for_graph_error(response: httpx.Response) -> None:
    """If Graph returned an error envelope, surface it as MetaGraphError.

    Graph occasionally returns 200 with an error body when paging hits a
    permissions snag, so we check the body regardless of HTTP status.
    """
    try:
        body = response.json()
    except ValueError:
        if response.status_code >= 400:
            raise MetaGraphError(
                f"Graph API returned non-JSON {response.status_code}: "
                f"{response.text[:200]}",
                http_status=response.status_code,
            )
        return

    err = body.get("error") if isinstance(body, dict) else None
    if err:
        raise MetaGraphError(
            err.get("message") or "Graph API error",
            code=err.get("code"),
            sub_code=err.get("error_subcode"),
            type_=err.get("type"),
            http_status=response.status_code,
            fbtrace_id=err.get("fbtrace_id"),
        )
    if response.status_code >= 400:
        raise MetaGraphError(
            f"Graph API HTTP {response.status_code} without error envelope: "
            f"{response.text[:200]}",
            http_status=response.status_code,
        )


def graph_get(
    path: str,
    *,
    access_token: str,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
    settings=None,
) -> dict[str, Any]:
    """Single Graph API GET.

    ``path`` is everything after the version (``/me``, ``/me/accounts``,
    ``/{page_id}/feed``). The access token is appended as a query param.
    """
    full = f"{_base_url(settings=settings)}{path if path.startswith('/') else '/' + path}"
    merged = dict(params or {})
    merged["access_token"] = access_token
    with httpx.Client(timeout=timeout) as client:
        response = client.get(full, params=merged)
    _raise_for_graph_error(response)
    return response.json()


def graph_paged(
    path: str,
    *,
    access_token: str,
    params: dict[str, Any] | None = None,
    page_limit: int = 5,
    timeout: float = 30.0,
    settings=None,
) -> Iterator[dict[str, Any]]:
    """Yield rows from a paged Graph endpoint, following ``paging.next``.

    Stops after ``page_limit`` HTTP requests to bound runtime — most
    callers cap by ``limit`` on the entity query anyway.
    """
    next_url: str | None = None
    next_params: dict[str, Any] | None = dict(params or {})
    if next_params is not None:
        next_params["access_token"] = access_token

    full = f"{_base_url(settings=settings)}{path if path.startswith('/') else '/' + path}"

    pages_fetched = 0
    with httpx.Client(timeout=timeout) as client:
        while pages_fetched < page_limit:
            if next_url is None:
                response = client.get(full, params=next_params)
            else:
                # ``paging.next`` already has access_token baked in.
                response = client.get(next_url)
            _raise_for_graph_error(response)
            body = response.json()
            for row in body.get("data") or []:
                yield row
            paging = body.get("paging") or {}
            next_url = paging.get("next")
            next_params = None
            pages_fetched += 1
            if not next_url:
                return


def exchange_short_for_long_lived(
    *,
    short_lived_token: str,
    client_id: str,
    client_secret: str,
    timeout: float = 30.0,
    settings=None,
) -> dict[str, Any]:
    """Swap a user short-lived token (≈1-2h) for a long-lived one (≈60d).

    Graph's official ``fb_exchange_token`` endpoint. The return body is
    ``{"access_token": "...", "token_type": "bearer", "expires_in": 5183944}``.
    """
    response = httpx.get(
        f"{_base_url(settings=settings)}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "fb_exchange_token": short_lived_token,
        },
        timeout=timeout,
    )
    _raise_for_graph_error(response)
    return response.json()


def exchange_code_for_token(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    timeout: float = 30.0,
    settings=None,
) -> dict[str, Any]:
    """OAuth code → user access token. First step of the consent flow.

    The returned token is **short-lived** by default; callers should
    swap it for a long-lived one with ``exchange_short_for_long_lived``.
    """
    response = httpx.get(
        f"{_base_url(settings=settings)}/oauth/access_token",
        params={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=timeout,
    )
    _raise_for_graph_error(response)
    return response.json()


# ─── App-level scope discovery ────────────────────────────────────────
#
# The "kitchen sink" scope catalog covers every read+write permission
# that the Use Cases on the Meta App Dashboard typically enable. We
# request all of them at consent time; Facebook silently filters out
# scopes the app isn't approved for and only renders the ones available.
# This is the right posture in dev mode because:
#
# 1. App Admins / Developers / Testers (which is the user) can grant
#    ANY scope the app has configured, with or without App Review.
# 2. Scopes the app DOESN'T have configured (because the corresponding
#    Use Case wasn't enabled) just don't appear in the consent dialog.
# 3. Users only consent ONCE — adding scopes here today means future
#    write features land without a second consent round trip.
#
# When an explicit env var ``META_OAUTH_SCOPES`` is set to a real list
# (not "auto" / not empty), the OAuth start endpoint uses that verbatim
# instead. Set to ``auto`` (or leave empty) for kitchen-sink behavior.
META_KITCHEN_SINK_SCOPES = [
    # Identity
    "public_profile",
    "email",
    # Facebook Pages — read
    "pages_show_list",
    "pages_read_engagement",
    "pages_read_user_content",
    # Facebook Pages — write
    "pages_manage_posts",
    "pages_manage_metadata",
    "pages_manage_engagement",
    "pages_messaging",
    # Instagram — read
    "instagram_basic",
    "instagram_manage_insights",
    # Instagram — write
    "instagram_content_publish",
    "instagram_manage_comments",
    "instagram_manage_messages",
    # Business assets (cross-account)
    "business_management",
]


def app_access_token(app_id: str, app_secret: str) -> str:
    """Facebook app access token = ``{APP_ID}|{APP_SECRET}`` concatenated.

    Documented at developers.facebook.com/docs/facebook-login/security/#appsecret.
    Used for app-admin endpoints (permissions catalog, app metadata,
    webhook subscriptions). Never expose this server-side token to a
    browser — it has full app-management authority.
    """
    return f"{app_id}|{app_secret}"


def discover_app_permissions(
    *,
    app_id: str,
    app_secret: str,
    timeout: float = 20.0,
    settings=None,
) -> list[str]:
    """Ask Graph which permissions are configured/approved on the app.

    Returns a list of permission names (e.g. ``["pages_show_list", ...]``).
    Falls back to :data:`META_KITCHEN_SINK_SCOPES` if Graph returns
    empty or errors — which is common when the app hasn't submitted any
    Use Case for App Review yet (dev mode behavior).
    """
    token = app_access_token(app_id, app_secret)
    try:
        body = graph_get(
            f"/{app_id}/permissions",
            access_token=token,
            timeout=timeout,
            settings=settings,
        )
    except MetaGraphError:
        return list(META_KITCHEN_SINK_SCOPES)

    rows = body.get("data") or []
    perms = [
        row["permission"]
        for row in rows
        if isinstance(row, dict)
        and row.get("permission")
        and row.get("status") in (None, "live", "approved", "in_review", "submitted")
    ]
    if not perms:
        return list(META_KITCHEN_SINK_SCOPES)
    return perms


def resolve_oauth_scopes(*, configured: str, app_id: str, app_secret: str) -> list[str]:
    """Decide what scope list to use for the consent URL.

    - If ``configured`` is empty or ``"auto"`` → discover from Graph
      (falls back to kitchen-sink list when Graph returns empty).
    - Else split the comma-separated env value verbatim.

    Returns the scope list with whitespace stripped + duplicates removed,
    preserving the first occurrence's order.
    """
    raw = (configured or "").strip()
    if raw and raw.lower() != "auto":
        candidates = [s.strip() for s in raw.split(",") if s.strip()]
    else:
        candidates = discover_app_permissions(app_id=app_id, app_secret=app_secret)

    seen: set[str] = set()
    out: list[str] = []
    for s in candidates:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out
