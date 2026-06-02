"""``noctus.youtube.snapshot_run`` / ``noctus.youtube.sync`` — trigger a fresh snapshot.

Sends ``POST /api/youtube/snapshot/run?account_id=<id>`` to the social-wiring
product API.  This is an action tool that initiates a live YouTube Data API
pull — the read tools (channel_stats, list_videos, report) query the data
that previous runs have already stored.

Auth / base-URL decision
------------------------
The snapshot endpoint requires a valid api_token from the
``social_wiring.api_tokens`` table.  However, the MCP toolkit has no
mechanism to obtain or store a product-scoped api_token at this time:

  - The token is a random hex secret stored per-org in ``api_tokens``; it
    is created by a user in the product UI.
  - The MCP toolkit does NOT have a service-account token baked in (that
    would be a security architecture decision beyond the scope of this slice).
  - The base URL for the social-wiring product API is not a constant in the
    MCP environment (it varies by dev vs prod deployment).

Both blockers are flagged and tracked:
  ``# NOC-REMEDIATE[yt-mcp-sync-auth]``

Until resolved, this tool returns a structured ``status: stub`` response that
explains EXACTLY how to trigger the snapshot manually, so the agent can
relay the instruction to the user.

When auth is available the implementation is a simple ``httpx.post`` (or
``requests.post`` if httpx is absent) to the product API with
``Authorization: Bearer <token>`` — the stub below is wired to upgrade
without structural changes.

Parameters
----------
account : str
    Resolve by UUID, label, or empty for auto-select.
api_token : str
    Product api_token with ``youtube:snapshot`` scope.
    Pass explicitly — the MCP toolkit does not store this automatically.
base_url : str
    Social-wiring product base URL (e.g. ``https://social-wiring.noctus.ai``).
    Pass explicitly — the MCP toolkit does not resolve product URLs.

Returns
-------
dict  — one of:

    Stub (auth/base-URL not configured)::

        {
          "status": "stub",
          "tool": "noctus.youtube.snapshot_run",
          "message": "...",
          "remediation": "NOC-REMEDIATE[yt-mcp-sync-auth]",
          "manual_trigger": {
            "method": "POST",
            "url": "/api/youtube/snapshot/run?account_id=<id>",
            "auth": "Authorization: Bearer <api_token>",
          },
        }

    Success (when both api_token + base_url are provided)::

        {
          "status": "triggered",
          "account_id": "<uuid>",
          "http_status": 200,
          "response": {...},
        }

    Account not found / not configured: structured ``error`` dict.
"""
from __future__ import annotations

import logging

from ._db import get_yt_client, _not_configured_error
from ._resolve import resolve_account

logger = logging.getLogger(__name__)

# NOC-REMEDIATE[yt-mcp-sync-auth]: snapshot_run and sync require product api_token
# + product base URL.  Until those are available in the MCP environment this tool
# returns a stub with manual instructions.  Upgrade path: when the platform ships
# a service-account token and a product URL registry, replace _STUB_RESPONSE with
# an httpx.post call to ``{base_url}/api/youtube/snapshot/run?account_id={id}``.


def snapshot_run(
    account: str = "",
    api_token: str = "",
    base_url: str = "",
) -> dict:
    """Trigger a fresh YouTube snapshot for an account.

    Parameters
    ----------
    account : str
        Account specifier — UUID, label, or empty for auto-select.
    api_token : str
        Product api_token with youtube:snapshot scope.  Required to call
        the product API.  If absent, returns a stub with manual instructions.
    base_url : str
        Social-wiring product base URL.  If absent, returns a stub.

    Returns
    -------
    dict
        ``status: triggered`` on success, or ``status: stub`` when
        api_token/base_url are not provided (with manual-trigger instructions).
    """
    # ── Resolve the account (so we can surface the account_id in the stub) ──
    try:
        client = get_yt_client()
        acc = resolve_account(client, account or None)
    except RuntimeError:
        acc = None

    account_id: str | None = None
    if acc and "error" not in acc:
        account_id = acc["id"]
    elif acc is not None and "error" in acc:
        return {
            "error": "account_not_found",
            "account": account,
            "message": "No active YouTube account matched the specifier.",
            "detail": acc,
        }

    # ── If full auth info provided, attempt the real call ────────────────────
    if api_token and base_url and account_id:
        try:
            return _do_trigger(base_url=base_url, account_id=account_id, api_token=api_token)
        except Exception as exc:  # noqa: BLE001
            logger.error("snapshot_run: HTTP trigger failed: %s", exc)
            return {
                "error": "trigger_failed",
                "account_id": account_id,
                "message": str(exc),
            }

    # ── Stub response ────────────────────────────────────────────────────────
    _id_hint = account_id or "<account_id>"
    return {
        "status": "stub",
        "tool": "noctus.youtube.snapshot_run",
        "account_id": account_id,
        "message": (
            "snapshot_run is not fully wired yet — the MCP toolkit does not have "
            "a product api_token or social-wiring base URL available automatically. "
            "Pass `api_token` and `base_url` explicitly to trigger a live pull, "
            "or trigger manually using the instructions in `manual_trigger`."
        ),
        "remediation": "NOC-REMEDIATE[yt-mcp-sync-auth]",
        "manual_trigger": {
            "method": "POST",
            "url": f"/api/youtube/snapshot/run?account_id={_id_hint}",
            "auth": "Authorization: Bearer <api_token>",
            "note": (
                "Create an api_token in the social-wiring Settings > API Tokens page, "
                "then POST to this endpoint with the token as a Bearer token."
            ),
        },
    }


def _do_trigger(*, base_url: str, account_id: str, api_token: str) -> dict:
    """Perform the actual HTTP trigger when credentials are available.

    Uses httpx if available, falls back to requests (both are optional deps
    in the MCP environment; neither is in the required dep set for the
    read-only tools).
    """
    url = f"{base_url.rstrip('/')}/api/youtube/snapshot/run"
    headers = {"Authorization": f"Bearer {api_token}"}
    params = {"account_id": account_id}

    try:
        import httpx  # type: ignore[import]

        with httpx.Client(timeout=30) as http:
            resp = http.post(url, headers=headers, params=params)
        return {
            "status": "triggered",
            "account_id": account_id,
            "http_status": resp.status_code,
            "response": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
        }
    except ImportError:
        pass

    import urllib.request
    import urllib.parse
    import json as _json

    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(full_url, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8")
    try:
        body_parsed = _json.loads(body)
    except Exception:
        body_parsed = body
    return {
        "status": "triggered",
        "account_id": account_id,
        "http_status": r.status,
        "response": body_parsed,
    }


def register(server) -> None:
    """Register ``noctus.youtube.snapshot_run`` and ``noctus.youtube.sync`` on the MCP server."""

    _description = (
        "Trigger a fresh YouTube Data API snapshot for an account. "
        "Sends POST /api/youtube/snapshot/run?account_id=<id> to the social-wiring product. "
        "Requires ``api_token`` (product api_token with youtube:snapshot scope) and "
        "``base_url`` (social-wiring product URL). "
        "Without those, returns a stub with manual-trigger instructions. "
        "NOC-REMEDIATE[yt-mcp-sync-auth]: automatic token/URL resolution not yet available. "
        "Read tools (channel_stats, list_videos, report) query already-stored data — "
        "use this to refresh before running a report."
    )

    @server.tool(
        name="noctus.youtube.snapshot_run",
        description=_description,
    )
    def _handler_run(
        account: str = "",
        api_token: str = "",
        base_url: str = "",
    ) -> dict:
        return snapshot_run(account=account, api_token=api_token, base_url=base_url)

    @server.tool(
        name="noctus.youtube.sync",
        description=_description + " Alias for noctus.youtube.snapshot_run.",
    )
    def _handler_sync(
        account: str = "",
        api_token: str = "",
        base_url: str = "",
    ) -> dict:
        return snapshot_run(account=account, api_token=api_token, base_url=base_url)
