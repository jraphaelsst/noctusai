"""Meta Graph HTTP plumbing — httpx-only, no SDK dependency.

Lifted verbatim-in-spirit from the live-validated workspace
`_meta_api.py`. Carries:

- `graph_get` / `graph_paged` — typed GET helpers (paged follows
  `paging.next` up to `max_pages`).
- `MetaGraphError` — typed exception with `is_auth_error` /
  `is_rate_limited` classifiers (consumers branch on these, never on
  raw codes).
- `_raise_for_graph_error` — Graph returns errors in a consistent
  envelope **even on `200 OK`**, so every response body is inspected.
- OAuth token-chain helpers: `exchange_code_for_token` (code →
  short-lived) + `exchange_for_long_lived` (short → ~60d).
- Scope auto-discovery: `META_KITCHEN_SINK_SCOPES`,
  `app_access_token`, `discover_app_permissions`,
  `resolve_oauth_scopes`.

Underscore-prefixed module: it's the adapter's private transport
layer, not part of the package's public surface.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from noctusai_lib.integrations.meta.types import TokenBundle

logger = logging.getLogger(__name__)

DEFAULT_GRAPH_VERSION = "v21.0"
GRAPH_BASE = "https://graph.facebook.com"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_PAGES = 5

# Auth-error Graph codes — token expired / revoked / wrong scope.
_AUTH_ERROR_CODES = {102, 190, 467}
# Rate-limit Graph codes — per-app / per-user / per-page throttles.
_RATE_LIMIT_CODES = {4, 17, 32, 613}
# Permission Graph codes — the token / app lacks the capability for a
# write or ads call. `10` = application does not have permission for
# this action; `200` = permissions error (scope not granted). On a
# write/ads path this almost always means the requested scope is gated
# behind Meta App Review and has not been approved for the app. The
# adapter surfaces this as `MetaGraphError.requires_app_review` so the
# consumer can tell "needs App-Review-approved scope" apart from
# "token expired" (`is_auth_error`) — never a silent or faked success.
_PERMISSION_ERROR_CODES = {10, 200}

# Kitchen-sink scope catalog. Versioned with the adapter, NOT in env
# (env-var scope lists drift across workspaces — session-notes §A.1
# Blocker 1). `resolve_oauth_scopes` falls back to this when Graph's
# app-permissions endpoint returns empty (pure dev mode, nothing
# submitted for review yet).
META_KITCHEN_SINK_SCOPES = [
    "public_profile",
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_metadata",
    "pages_read_user_content",
    "read_insights",
    "instagram_basic",
    "instagram_manage_insights",
    "instagram_manage_comments",
    "business_management",
]


class MetaGraphError(Exception):
    """Typed wrapper around a Graph error envelope.

    Consumers branch on `is_auth_error` (re-consent / re-issue token)
    and `is_rate_limited` (back off) — never on the raw `code`.
    `fbtrace_id` is Meta's support hand-off; log it when escalating."""

    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        error_subcode: int | None = None,
        error_type: str | None = None,
        fbtrace_id: str | None = None,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.error_subcode = error_subcode
        self.error_type = error_type
        self.fbtrace_id = fbtrace_id
        self.http_status = http_status

    @property
    def is_auth_error(self) -> bool:
        return self.code in _AUTH_ERROR_CODES

    @property
    def is_rate_limited(self) -> bool:
        return self.code in _RATE_LIMIT_CODES

    @property
    def is_permission(self) -> bool:
        """The token / app lacks the capability for this action.

        Distinct from `is_auth_error` (token expired / revoked — fix by
        re-issuing the token) — a permission error means the token is
        valid but the requested scope was never granted to it."""

        return self.code in _PERMISSION_ERROR_CODES

    @property
    def requires_app_review(self) -> bool:
        """A write / ads scope this call needs is gated behind Meta App
        Review and has not been approved for the app.

        Surfaced so the consumer can branch deterministically: this is
        a *production-activation* gate (submit the app for App Review,
        get the write/ads scope approved), NOT a code defect and NOT a
        transient error. Equal to `is_permission` — the permission
        codes (`10`, `200`) on a write/ads path always trace to an
        unapproved gated scope. Never raised as a silent or faked
        success — the write path fails loud with this flag set."""

        return self.is_permission

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"MetaGraphError(code={self.code}, subcode={self.error_subcode}, "
            f"type={self.error_type!r}, msg={self.message!r})"
        )


def _raise_for_graph_error(
    payload: Any, *, http_status: int | None = None
) -> None:
    """Raise `MetaGraphError` if `payload` carries a Graph error
    envelope. Graph returns errors even on 200 OK, so this runs on
    EVERY response. Non-dict / HTML bodies (e.g. a 503 gateway page)
    raise a generic `MetaGraphError` with the http status."""

    if not isinstance(payload, dict):
        if http_status is not None and http_status >= 400:
            raise MetaGraphError(
                f"Non-JSON Graph response (HTTP {http_status})",
                http_status=http_status,
            )
        return
    err = payload.get("error")
    if not isinstance(err, dict):
        return
    raise MetaGraphError(
        err.get("message", "Unknown Graph error"),
        code=err.get("code"),
        error_subcode=err.get("error_subcode"),
        error_type=err.get("type"),
        fbtrace_id=err.get("fbtrace_id"),
        http_status=http_status,
    )


def _parse_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return resp.text


def graph_get(
    path: str,
    *,
    access_token: str,
    params: dict[str, Any] | None = None,
    version: str = DEFAULT_GRAPH_VERSION,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """GET `{GRAPH_BASE}/{version}/{path}` with the token appended.

    `path` is version-relative (e.g. `"me"`, `"me/accounts"`,
    `"{page_id}/posts"`). Raises `MetaGraphError` on a Graph error
    envelope (even at HTTP 200) or a non-JSON body."""

    q: dict[str, Any] = dict(params or {})
    q["access_token"] = access_token
    url = f"{GRAPH_BASE}/{version}/{path.lstrip('/')}"
    resp = httpx.get(url, params=q, timeout=timeout)
    body = _parse_json(resp)
    _raise_for_graph_error(body, http_status=resp.status_code)
    if not isinstance(body, dict):
        raise MetaGraphError(
            f"Expected JSON object from {path}, got {type(body).__name__}",
            http_status=resp.status_code,
        )
    return body


def graph_paged(
    path: str,
    *,
    access_token: str,
    params: dict[str, Any] | None = None,
    version: str = DEFAULT_GRAPH_VERSION,
    max_pages: int = DEFAULT_MAX_PAGES,
    limit: int | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    """Follow `paging.next` and accumulate `data` rows, up to
    `max_pages`. `limit` (when set) truncates the accumulated list."""

    q: dict[str, Any] = dict(params or {})
    rows: list[dict[str, Any]] = []
    body = graph_get(
        path, access_token=access_token, params=q, version=version, timeout=timeout
    )
    rows.extend(body.get("data") or [])
    pages = 1
    next_url = (body.get("paging") or {}).get("next")
    while next_url and pages < max_pages:
        resp = httpx.get(next_url, timeout=timeout)
        nb = _parse_json(resp)
        _raise_for_graph_error(nb, http_status=resp.status_code)
        if not isinstance(nb, dict):
            break
        rows.extend(nb.get("data") or [])
        next_url = (nb.get("paging") or {}).get("next")
        pages += 1
    if limit is not None:
        return rows[:limit]
    return rows


def graph_post(
    path: str,
    *,
    access_token: str,
    data: dict[str, Any] | None = None,
    version: str = DEFAULT_GRAPH_VERSION,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """POST `{GRAPH_BASE}/{version}/{path}` with the token in the body.

    The write twin of `graph_get`. `path` is version-relative (e.g.
    `"{page_id}/feed"`, `"{ig_user_id}/media"`,
    `"{ig_user_id}/media_publish"`, `"act_{id}/campaigns"`). The
    token + form fields go in the POST body (Graph accepts
    form-encoded writes).

    Raises `MetaGraphError` on a Graph error envelope (even at HTTP
    200) or a non-JSON body. A permission / unapproved-scope failure
    surfaces as `MetaGraphError` with `is_permission` /
    `requires_app_review` true — the caller MUST NOT swallow it into a
    faked success (no-silent-errors)."""

    form: dict[str, Any] = dict(data or {})
    form["access_token"] = access_token
    url = f"{GRAPH_BASE}/{version}/{path.lstrip('/')}"
    resp = httpx.post(url, data=form, timeout=timeout)
    body = _parse_json(resp)
    _raise_for_graph_error(body, http_status=resp.status_code)
    if not isinstance(body, dict):
        raise MetaGraphError(
            f"Expected JSON object from {path}, got {type(body).__name__}",
            http_status=resp.status_code,
        )
    return body


def poll_media_status(
    creation_id: str,
    *,
    access_token: str,
    version: str = DEFAULT_GRAPH_VERSION,
    timeout_seconds: float = 90.0,
    poll_interval_seconds: float = 2.0,
    transient_retries: int = 3,
    sleep=time.sleep,
) -> "MediaProcessingStatus":
    """Poll a video / Reel media container until it is publish-ready.

    The IG Reel / FB video publish flow is asynchronous: the container
    create (``media_type=REELS`` / ``/video_reels``) returns a creation
    id whose ``status_code`` is ``IN_PROGRESS`` while Graph transcodes.
    This polls ``GET /{creation-id}?fields=status,status_code`` every
    ``poll_interval_seconds`` until the status is terminal:

    - ``FINISHED`` (or ``PUBLISHED``) → returns the
      ``MediaProcessingStatus`` so the caller proceeds to
      ``media_publish``.
    - ``ERROR`` / ``EXPIRED`` → raises ``MetaGraphError`` (the transcode
      failed or the upload window lapsed) — **never** a silent or faked
      ready signal (no-silent-errors).
    - timeout (``timeout_seconds`` elapsed without a terminal status) →
      raises ``MetaGraphError("video_processing_timeout", ...)`` — the
      poll loop is hard-capped and never blocks indefinitely (the same
      gated-capability-honesty discipline as the App-Review gate).

    Transient HTTP 5xx during a status read are retried up to
    ``transient_retries`` times within the overall timeout budget
    (Graph's status endpoint occasionally 5xx's mid-transcode);
    permission / auth errors are NOT retried — they re-raise immediately
    (an unapproved scope or a dead token will not recover by polling).

    ``sleep`` is injected (defaults to ``time.sleep``) so tests drive the
    loop deterministically with zero wall-clock wait. The Graph boundary
    itself (``graph_get``) is patched in tests, never this function."""

    from noctusai_lib.integrations.meta.types import MediaProcessingStatus

    deadline = time.monotonic() + timeout_seconds
    transient_left = transient_retries
    while True:
        try:
            body = graph_get(
                creation_id,
                access_token=access_token,
                params={"fields": "status,status_code"},
                version=version,
            )
        except MetaGraphError as exc:
            # Permission / auth failures will not recover by polling —
            # re-raise loud so the App-Review gate / re-consent surfaces.
            if exc.is_permission or exc.is_auth_error:
                raise
            # Transient (5xx / network) — retry within the timeout budget.
            transient_left -= 1
            if transient_left < 0 or time.monotonic() >= deadline:
                raise MetaGraphError(
                    f"Media container {creation_id} status read failed "
                    f"after {transient_retries} transient retries: "
                    f"{exc.message}",
                    code=exc.code,
                    http_status=exc.http_status,
                )
            sleep(poll_interval_seconds)
            continue
        status_code = str(body.get("status_code") or "").upper()
        result = MediaProcessingStatus(
            creation_id=creation_id,
            status_code=status_code,
            status=body.get("status"),
            raw=dict(body),
        )
        if result.is_error:
            raise MetaGraphError(
                f"Media container {creation_id} processing failed "
                f"(status_code={status_code!r}, status={body.get('status')!r})",
                code=body.get("code"),
            )
        if result.is_finished:
            return result
        # Still IN_PROGRESS — wait, then re-poll if there is budget left.
        if time.monotonic() >= deadline:
            raise MetaGraphError(
                f"video_processing_timeout: media container {creation_id} "
                f"not FINISHED within {timeout_seconds:g}s "
                f"(last status_code={status_code!r})",
            )
        sleep(poll_interval_seconds)


def exchange_code_for_token(
    *,
    code: str,
    app_id: str,
    app_secret: str,
    redirect_uri: str,
    version: str = DEFAULT_GRAPH_VERSION,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Step 2 of the token chain: authorization `code` → short-lived
    (~2h) user access token.

    Returns only the token string (back-compat). Use
    `exchange_code_for_token_bundle` to also capture `expires_in` /
    `token_type`."""

    return exchange_code_for_token_bundle(
        code=code,
        app_id=app_id,
        app_secret=app_secret,
        redirect_uri=redirect_uri,
        version=version,
        timeout=timeout,
    ).access_token


def exchange_for_long_lived(
    *,
    short_token: str,
    app_id: str,
    app_secret: str,
    version: str = DEFAULT_GRAPH_VERSION,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Step 3 of the token chain: short-lived → long-lived (~60d) user
    token via `grant_type=fb_exchange_token`. Mandatory — a 2h token
    is unusable for any production workflow.

    Returns only the token string (back-compat). Use
    `exchange_for_long_lived_bundle` to also capture `expires_in` /
    `token_type`."""

    return exchange_for_long_lived_bundle(
        short_token=short_token,
        app_id=app_id,
        app_secret=app_secret,
        version=version,
        timeout=timeout,
    ).access_token


def _token_bundle_from_body(body: dict[str, Any]) -> TokenBundle:
    """Map a Graph `oauth/access_token` response body to a `TokenBundle`.

    `access_token` is required (the error envelope is raised upstream);
    `expires_in` / `token_type` are optional — the short-lived code
    exchange may omit them. `expires_in` is coerced to int when present
    (Graph returns it as a number; a string slips through as-is only if
    Graph ever changes — defensive int())."""

    expires_in = body.get("expires_in")
    if expires_in is not None:
        expires_in = int(expires_in)
    return TokenBundle(
        access_token=body["access_token"],
        expires_in=expires_in,
        token_type=body.get("token_type"),
    )


def exchange_code_for_token_bundle(
    *,
    code: str,
    app_id: str,
    app_secret: str,
    redirect_uri: str,
    version: str = DEFAULT_GRAPH_VERSION,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> TokenBundle:
    """Step 2 of the token chain, full-metadata variant: authorization
    `code` → short-lived (~2h) user access token, returned as a
    `TokenBundle` carrying `access_token` plus the `expires_in` /
    `token_type` Graph returns (the short-lived exchange may omit
    `expires_in`, so it is None-safe). `exchange_code_for_token`
    delegates to this and returns just `.access_token`."""

    resp = httpx.get(
        f"{GRAPH_BASE}/{version}/oauth/access_token",
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=timeout,
    )
    body = _parse_json(resp)
    _raise_for_graph_error(body, http_status=resp.status_code)
    return _token_bundle_from_body(body)


def exchange_for_long_lived_bundle(
    *,
    short_token: str,
    app_id: str,
    app_secret: str,
    version: str = DEFAULT_GRAPH_VERSION,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> TokenBundle:
    """Step 3 of the token chain, full-metadata variant: short-lived →
    long-lived (~60d) user token via `grant_type=fb_exchange_token`,
    returned as a `TokenBundle`. The long-lived response carries
    `expires_in` (~60d in seconds) + `token_type` — preserved here so
    the caller can compute a refresh deadline.
    `exchange_for_long_lived` delegates to this and returns just
    `.access_token`."""

    resp = httpx.get(
        f"{GRAPH_BASE}/{version}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
        timeout=timeout,
    )
    body = _parse_json(resp)
    _raise_for_graph_error(body, http_status=resp.status_code)
    return _token_bundle_from_body(body)


# ─── Scope auto-discovery ─────────────────────────────────────────────────


def app_access_token(app_id: str, app_secret: str) -> str:
    """The App Access Token is literally `{app_id}|{app_secret}` — no
    network call. Used to query the app-permissions endpoint."""

    return f"{app_id}|{app_secret}"


def discover_app_permissions(
    *,
    app_id: str,
    app_secret: str,
    version: str = DEFAULT_GRAPH_VERSION,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[str] | None:
    """Query `GET /{app-id}/permissions` with the App Access Token to
    discover the scopes the app is approved for.

    Returns the discovered scope list, or `None` when Graph returns an
    empty set (common in pure dev mode — nothing submitted for review)
    so the caller falls back to `META_KITCHEN_SINK_SCOPES`. Network /
    Graph failure also yields `None` (logged at WARNING) — discovery
    is best-effort, the kitchen-sink is the safety net."""

    try:
        body = graph_get(
            f"{app_id}/permissions",
            access_token=app_access_token(app_id, app_secret),
            version=version,
            timeout=timeout,
        )
    except (MetaGraphError, httpx.HTTPError) as exc:
        logger.warning("Meta app-permissions discovery failed: %s", exc)
        return None
    rows = body.get("data") or []
    scopes = [
        r["permission"]
        for r in rows
        if isinstance(r, dict)
        and r.get("permission")
        and r.get("status") in (None, "live", "approved")
    ]
    return scopes or None


def resolve_oauth_scopes(
    *,
    configured: str | None,
    app_id: str | None = None,
    app_secret: str | None = None,
    version: str = DEFAULT_GRAPH_VERSION,
) -> list[str]:
    """Resolve the OAuth scope request set.

    - Explicit comma-separated list → used verbatim.
    - Empty or `"auto"` → `discover_app_permissions(...)` when app
      creds are present, else `META_KITCHEN_SINK_SCOPES`.

    Removes the per-workspace env-var maintenance trap (session-notes
    §A.1 Blocker 1). `<PROVIDER>_OAUTH_SCOPES=auto` is the documented
    `.env.example` default."""

    raw = (configured or "").strip()
    if raw and raw.lower() != "auto":
        return [s.strip() for s in raw.split(",") if s.strip()]
    if app_id and app_secret:
        discovered = discover_app_permissions(
            app_id=app_id, app_secret=app_secret, version=version
        )
        if discovered:
            return discovered
    return list(META_KITCHEN_SINK_SCOPES)


__all__ = [
    "DEFAULT_GRAPH_VERSION",
    "DEFAULT_MAX_PAGES",
    "GRAPH_BASE",
    "META_KITCHEN_SINK_SCOPES",
    "MetaGraphError",
    "app_access_token",
    "discover_app_permissions",
    "exchange_code_for_token",
    "exchange_code_for_token_bundle",
    "exchange_for_long_lived",
    "exchange_for_long_lived_bundle",
    "graph_get",
    "graph_paged",
    "graph_post",
    "poll_media_status", "resolve_oauth_scopes",
]
