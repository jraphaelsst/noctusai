"""Cloudflare API v4 runner — the external-service seam for this connector.

Every `cloudflare.*` tool talks to the Cloudflare API v4
(`https://api.cloudflare.com/client/v4`) *through the operator's Bearer
token*. `request_json` is the single HTTP boundary (stdlib `urllib` —
zero extra deps, the same "wrap the stdlib" discipline `mcp/n8n` /
`mcp/waha` / `mcp/hostinger` apply).

**Test seam.** Cloudflare is an external service, so tests
`unittest.mock.patch("cloudflare.api.request_json", ...)` to feed
canned payloads without a network call — sanctioned by CLAUDE.md §1
("monkeypatching ... for external services ... is fine"). Our own code
is never patched.

**The Cloudflare envelope.** Cloudflare wraps EVERY response in
`{"success": bool, "errors": [...], "messages": [...], "result": ...,
"result_info": {...}}`. A 200 with `success:false` is still a failure
(e.g. validation error). `request_json` therefore inspects the envelope:
on `success:false` it raises `CloudflareApiError` carrying the first
`errors[].code` + `message` (gated-capability honesty — never a
fabricated success); on `success:true` it returns the `result` (plus
`result_info` is exposed via `request_envelope` for paginated reads).

**Gated-capability honesty** (CLAUDE.md §1). No API token, an
unreachable host, an upstream non-2xx, or a `success:false` envelope is
a typed, never-faked signal: tools return a `CloudflareApiError`
envelope (status carried), and
`cloudflare.diagnostics.connection_status` reports `configured=false` /
`reachable=false` / `authenticated=false`. We never fabricate success.

**Cloudflare WAF — `User-Agent` is load-bearing.** Cloudflare's own
edge WAF blocks the default `Python-urllib/x.y` user-agent on some
paths (the just-built `mcp/hostinger` hit exactly this against a
Cloudflare-fronted host — HTTP 403 *before the request reaches the API*,
NOT an auth failure). `request_json` therefore sends a browser-style
`User-Agent` on every call — a connectivity prerequisite, not
impersonation. Auth is header `Authorization: Bearer <token>`.

Paths are **absolute** under the fixed v4 base (`/zones`,
`/accounts/{id}/cfd_tunnel`, ...) — `normalize_base_url` only strips a
trailing slash and supplies the canonical base when unset (mirrors
WAHA/hostinger absolute paths, unlike n8n's `/api/v1` suffix).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

# Canonical Cloudflare API v4 base. Effectively fixed (a single public
# API), but kept overridable via settings for testing.
DEFAULT_BASE_URL = "https://api.cloudflare.com/client/v4"

# Cloudflare's edge WAF can ban the default `Python-urllib/x.y` UA before
# auth is even evaluated (Error 1010, observed via `mcp/hostinger` against
# a Cloudflare-fronted host). A browser-style UA pre-empts the same here.
# This is a connectivity prerequisite, not impersonation.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class CloudflareApiError(Exception):
    """A Cloudflare API call could not produce a real result.

    `status` feeds the connector-MCP typed-error contract
    (`_kit.errors.typed_error` reads `getattr(e, "status", None)`):

    - 412 — confirmation required (write gate; raised by the tool layer)
    - 424 — connector not configured (no API token)
    - 401/403/404/422/4xx/5xx — the upstream Cloudflare HTTP status,
      passed through (a 403 may also be Cloudflare's WAF block — see
      module docstring)
    - 502 — host unreachable / timeout / unparseable (non-JSON) response

    `cf_code` carries the first Cloudflare `errors[].code` when the
    failure is a `success:false` envelope (200-OK transport, business
    error) so the host LLM can branch on the Cloudflare-specific code.
    """

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        cf_code: Optional[int] = None,
    ):
        super().__init__(message)
        self.status = status
        self.cf_code = cf_code


class ConfirmationRequiredError(CloudflareApiError):
    """A write tool was called without `confirm=true`.

    No side-effect is performed — the host LLM must re-call with
    `confirm=true` (confirm-then-execute, `KB § PATTERNS/llm-bot-security.md`).
    The message states the concrete effect so the operator understands
    what they are authorizing (esp. the strongest gates `dns.delete_record`
    and `tunnel.delete`, which are outward-facing / irreversible).
    """

    def __init__(self, action: str, effect: str = ""):
        super().__init__(
            f"'{action}' is a write action"
            + (f" — {effect}" if effect else "")
            + ". Re-call with confirm=true to perform it. NO side-effect "
            "was performed.",
            status=412,
        )


def normalize_base_url(raw: str) -> str:
    """Return the API base with no trailing slash.

    Empty / unset ⇒ the canonical `DEFAULT_BASE_URL` (the Cloudflare API
    v4 is a single public host). Cloudflare paths are absolute (`/zones`,
    `/accounts/{id}/cfd_tunnel`) — there is no per-call suffix to
    normalize (mirrors WAHA/hostinger, unlike n8n).
    """
    base = (raw or "").rstrip("/")
    return base or DEFAULT_BASE_URL


def _first_cf_error(envelope: dict) -> tuple[Optional[int], str]:
    """Extract `(code, message)` from the first entry of a Cloudflare
    `errors` array. Tolerant of a missing / oddly-shaped array — never
    raises, so a `success:false` with no usable detail still surfaces a
    generic message rather than crashing the seam."""
    errs = envelope.get("errors")
    if isinstance(errs, list) and errs:
        first = errs[0]
        if isinstance(first, dict):
            code = first.get("code")
            msg = first.get("message") or ""
            return (code if isinstance(code, int) else None, str(msg))
    return None, ""


def request_envelope(
    method: str,
    path: str,
    *,
    api_token: str,
    base_url: str = "",
    params: Optional[dict] = None,
    body: Optional[object] = None,
    timeout: float = 20.0,
) -> dict:
    """Call `<base><path>` and return the FULL parsed Cloudflare envelope.

    Use this when the caller needs `result_info` (pagination) alongside
    `result`. `success:false` is still raised as a `CloudflareApiError`
    (transport may be 200; the envelope is the truth) — so even this
    "full envelope" form never returns a fabricated success.

    `api_token` comes from the connector settings (resolved by the tool
    layer). Missing it is the connector-not-configured signal (424).
    Sends `Authorization: Bearer <token>` + a browser-style `User-Agent`.
    Raises `CloudflareApiError` (typed `status` / `cf_code`) on ANY
    failure.
    """
    if not api_token:
        raise CloudflareApiError(
            "Cloudflare connector not configured — set CLOUDFLARE_API_TOKEN "
            "in mcp/cloudflare/.env (or the environment).",
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
        # Load-bearing: clears the Cloudflare WAF (see module docstring).
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
        # Cloudflare encodes the real cause in the JSON body's `errors`;
        # surface the first code + message when parseable, else a snippet.
        detail = ""
        cf_code = None
        try:
            body_text = e.read().decode("utf-8", errors="replace")
            parsed = json.loads(body_text)
            if isinstance(parsed, dict):
                cf_code, msg = _first_cf_error(parsed)
                detail = msg or body_text[:500]
            else:
                detail = body_text[:500]
        except Exception:  # noqa: BLE001 — body read is best-effort context
            detail = ""
        raise CloudflareApiError(
            f"Cloudflare API {method.upper()} {path} → HTTP {e.code}"
            + (f": {detail}" if detail else ""),
            status=e.code,
            cf_code=cf_code,
        ) from e
    except urllib.error.URLError as e:
        raise CloudflareApiError(
            f"Cloudflare host unreachable for {method.upper()} {path}: "
            f"{e.reason}",
            status=502,
        ) from e
    except TimeoutError as e:
        raise CloudflareApiError(
            f"Cloudflare API {method.upper()} {path} timed out after "
            f"{timeout}s",
            status=502,
        ) from e

    if not raw:
        # An empty body with a 2xx is unusual for Cloudflare (it always
        # wraps in the envelope) but tolerate it as an empty success.
        return {"success": True, "errors": [], "messages": [], "result": None}
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as e:
        raise CloudflareApiError(
            f"Cloudflare API {method.upper()} {path} returned non-JSON output",
            status=502,
        ) from e

    if not isinstance(envelope, dict):
        raise CloudflareApiError(
            f"Cloudflare API {method.upper()} {path} returned a "
            f"non-envelope JSON ({type(envelope).__name__})",
            status=502,
        )

    if not envelope.get("success", False):
        cf_code, msg = _first_cf_error(envelope)
        raise CloudflareApiError(
            f"Cloudflare API {method.upper()} {path} returned success=false"
            + (f" (code {cf_code})" if cf_code is not None else "")
            + (f": {msg}" if msg else ""),
            status=200,
            cf_code=cf_code,
        )
    return envelope


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
    """Call `<base><path>` and return the Cloudflare envelope's `result`.

    The common case (the caller only wants `result`, not pagination
    info). Delegates to `request_envelope` for the full transport +
    envelope handling, then unwraps `result`. Same typed-error contract.
    """
    envelope = request_envelope(
        method,
        path,
        api_token=api_token,
        base_url=base_url,
        params=params,
        body=body,
        timeout=timeout,
    )
    return envelope.get("result")


__all__ = [
    "request_json",
    "request_envelope",
    "normalize_base_url",
    "CloudflareApiError",
    "ConfirmationRequiredError",
    "DEFAULT_BASE_URL",
]
