"""Hostinger API runner — the external-service seam for this connector.

Every `hostinger.*` tool talks to the Hostinger Developers API
(`https://developers.hostinger.com`) *through the operator's Bearer
token*. `request_json` is the single HTTP boundary (stdlib `urllib` —
zero extra deps, the same "wrap the stdlib" discipline `mcp/n8n` and
`mcp/waha` apply).

**Test seam.** Hostinger is an external service, so tests
`unittest.mock.patch("hostinger.api.request_json", ...)` to feed canned
payloads without a network call — sanctioned by CLAUDE.md §1
("monkeypatching ... for external services ... is fine"). Our own code
is never patched.

**Gated-capability honesty** (CLAUDE.md §1). No API token, an
unreachable host, or an upstream non-2xx is a typed, never-faked
signal: tools return a `HostingerApiError` envelope (status carried),
and `hostinger.diagnostics.connection_status` reports
`configured=false` / `reachable=false` / `authenticated=false`. We
never fabricate success.

**Cloudflare WAF — `User-Agent` is load-bearing.** Unlike the
self-hosted WAHA / n8n instances, `developers.hostinger.com` sits
behind Cloudflare, which **blocks the default `Python-urllib/x.y`
user-agent** (returns HTTP 403 "Error 1010: browser_signature_banned"
*before the request ever reaches the API* — it is NOT an auth failure).
`request_json` therefore sends a browser-style `User-Agent`. Verified
live 2026-05-21: default UA → 403/1010; browser UA → 200. Auth is
header `Authorization: Bearer <token>`.

Paths are **absolute** under the fixed host (`/api/vps/v1/...`) — like
WAHA there is no normalizing suffix; `normalize_base_url` only strips a
trailing slash and supplies the canonical Hostinger host when unset.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

# Canonical Hostinger Developers API host. The base_url is effectively
# fixed (a single public API, not a per-tenant instance) but kept
# overridable via settings for testing / future regional hosts.
DEFAULT_BASE_URL = "https://developers.hostinger.com"

# Cloudflare in front of developers.hostinger.com bans the default
# `Python-urllib/x.y` UA (Error 1010) before auth is even evaluated.
# A browser-style UA is required for ANY call to succeed (verified live
# 2026-05-21). This is a connectivity prerequisite, not impersonation.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class HostingerApiError(Exception):
    """A Hostinger API call could not produce a real result.

    `status` feeds the connector-MCP typed-error contract
    (`_kit.errors.typed_error` reads `getattr(e, "status", None)`):

    - 412 — confirmation required (write/power gate; raised by the tool layer)
    - 424 — connector not configured (no API token)
    - 401/403/404/422/4xx/5xx — the upstream Hostinger HTTP status, passed
      through (a 403 may also be Cloudflare's WAF block — see module docstring)
    - 502 — host unreachable / timeout / unparseable (non-JSON) response
    """

    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ConfirmationRequiredError(HostingerApiError):
    """A write/power tool was called without `confirm=true`.

    No side-effect is performed — the host LLM must re-call with
    `confirm=true` (confirm-then-execute, `KB § PATTERNS/llm-bot-security.md`).
    The message states the concrete effect so the operator understands
    what they are authorizing (esp. `stop`, which takes the server down).
    """

    def __init__(self, action: str, effect: str = ""):
        super().__init__(
            f"'{action}' is a write/power action"
            + (f" — {effect}" if effect else "")
            + ". Re-call with confirm=true to perform it. NO side-effect "
            "was performed.",
            status=412,
        )


def normalize_base_url(raw: str) -> str:
    """Return the API host with no trailing slash.

    Empty / unset ⇒ the canonical `DEFAULT_BASE_URL` (the Hostinger
    Developers API is a single public host, not a per-tenant instance).
    Hostinger paths are absolute (`/api/vps/v1/...`) — there is no
    `/api/v1`-style suffix to normalize (mirrors WAHA's absolute paths,
    unlike n8n).
    """
    base = (raw or "").rstrip("/")
    return base or DEFAULT_BASE_URL


def request_json(
    method: str,
    path: str,
    *,
    api_token: str,
    base_url: str = "",
    params: Optional[dict] = None,
    body: Optional[object] = None,
    timeout: float = 20.0,
) -> object:
    """Call `<base><path>` and return parsed JSON.

    `api_token` comes from the connector settings (resolved by the tool
    layer). Missing it is the connector-not-configured signal (424).
    Sends `Authorization: Bearer <token>` + a browser-style `User-Agent`
    (required to clear Cloudflare — see module docstring). Raises
    `HostingerApiError` (typed `status`) on ANY failure — never returns
    a partial or fabricated success.
    """
    if not api_token:
        raise HostingerApiError(
            "Hostinger connector not configured — set HOSTINGER_API_TOKEN "
            "in mcp/hostinger/.env (or the environment).",
            status=424,
        )
    url = f"{normalize_base_url(base_url)}{path}"
    if params:
        # Drop None-valued params so callers can pass optional filters flatly.
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url = f"{url}?{urllib.parse.urlencode(clean)}"

    data: Optional[bytes] = None
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
        # Load-bearing: clears the Cloudflare WAF in front of the host.
        "User-Agent": _BROWSER_USER_AGENT,
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url, data=data, headers=headers, method=method.upper()
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # Hostinger encodes the real cause in the JSON body; surface a snippet.
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001 — body read is best-effort context
            detail = ""
        raise HostingerApiError(
            f"Hostinger API {method.upper()} {path} → HTTP {e.code}"
            + (f": {detail}" if detail else ""),
            status=e.code,
        ) from e
    except urllib.error.URLError as e:
        raise HostingerApiError(
            f"Hostinger host unreachable for {method.upper()} {path}: "
            f"{e.reason}",
            status=502,
        ) from e
    except TimeoutError as e:
        raise HostingerApiError(
            f"Hostinger API {method.upper()} {path} timed out after {timeout}s",
            status=502,
        ) from e

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise HostingerApiError(
            f"Hostinger API {method.upper()} {path} returned non-JSON output",
            status=502,
        ) from e


__all__ = [
    "request_json",
    "normalize_base_url",
    "HostingerApiError",
    "ConfirmationRequiredError",
    "DEFAULT_BASE_URL",
]
