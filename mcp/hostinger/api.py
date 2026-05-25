"""Hostinger API runner — the external-service seam for this connector.

Every `hostinger.*` tool talks to the Hostinger Developers API
(`https://developers.hostinger.com`) *through the operator's Bearer
token*. `request_json` is the single HTTP boundary; the urllib mechanics
are delegated to the shared `_kit.transport.request_json` seam
(kit-connector-boilerplate-consolidation). This wrapper keeps Hostinger's
own `HostingerApiError` type, the 424 not-configured gate, and the
canonical-host base-URL normalizer.

**Test seam.** Hostinger is an external service, so tests
`unittest.mock.patch("hostinger.api.request_json", ...)` to feed canned
payloads without a network call — sanctioned by CLAUDE.md §1
("monkeypatching ... for external services ... is fine"). The header /
transport tests patch the shared boundary `_kit.transport.urlopen`. Our
own code is never patched.

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
`request_json` therefore passes the shared `_kit.transport.BROWSER_USER_AGENT`.
Verified live 2026-05-21: default UA → 403/1010; browser UA → 200. Auth
is header `Authorization: Bearer <token>`.

Paths are **absolute** under the fixed host (`/api/vps/v1/...`) — like
WAHA there is no normalizing suffix; `normalize_base_url` only strips a
trailing slash and supplies the canonical Hostinger host when unset.
"""
from __future__ import annotations

from typing import Optional

from _kit.errors import confirmation_required_message
from _kit.transport import BROWSER_USER_AGENT
from _kit.transport import request_json as _http_request_json

# Canonical Hostinger Developers API host. The base_url is effectively
# fixed (a single public API, not a per-tenant instance) but kept
# overridable via settings for testing / future regional hosts.
DEFAULT_BASE_URL = "https://developers.hostinger.com"


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
            confirmation_required_message(action, effect, noun="write/power action"),
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
    # Delegate the urllib mechanics to the shared seam; Hostinger keeps its
    # own canonical-host normalizer + HostingerApiError type + the 424 gate.
    # The browser User-Agent is LOAD-BEARING — clears the Cloudflare WAF in
    # front of developers.hostinger.com (verified live 2026-05-21).
    url = f"{normalize_base_url(base_url)}{path}"
    return _http_request_json(
        method,
        url,
        auth_header=("Authorization", f"Bearer {api_token}"),
        user_agent=BROWSER_USER_AGENT,
        params=params,
        body=body,
        timeout=timeout,
        error_cls=HostingerApiError,
        empty_result={},
        label=f"Hostinger API {method.upper()} {path}",
    )


__all__ = [
    "request_json",
    "normalize_base_url",
    "HostingerApiError",
    "ConfirmationRequiredError",
    "DEFAULT_BASE_URL",
]
