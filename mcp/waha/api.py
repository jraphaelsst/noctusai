"""WAHA HTTP API runner — the external-service seam for this connector.

Every `waha.*` tool talks to the WAHA instance *through the operator's
`X-Api-Key`*. `request_json` is the single HTTP boundary (stdlib
`urllib` — zero extra deps, same discipline `mcp/n8n` applies).

**Test seam.** WAHA is an external service, so tests
`unittest.mock.patch("waha.api.request_json", ...)` to feed canned
payloads without a network call — sanctioned by CLAUDE.md §1
("monkeypatching ... for external services ... is fine"). Our own code
is never patched.

**Gated-capability honesty** (CLAUDE.md §1). No base-URL / API-key,
an unreachable host, or an upstream non-2xx is a typed, never-faked
signal: tools return a `WahaApiError` envelope (status carried), and
`waha.diagnostics.connection_status` reports `configured=false` /
`reachable=false` / `authenticated=false`. We never fabricate success.

Unlike n8n there is **no `/api/v1` prefix** — WAHA paths are absolute
(`/ping`, `/api/sessions`, `/api/sendText`); `normalize_base_url` only
strips a trailing slash. `/ping` is the one unauthenticated endpoint.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional


class WahaApiError(Exception):
    """A WAHA API call could not produce a real result.

    `status` feeds the connector-MCP typed-error contract
    (`_kit.errors.typed_error` reads `getattr(e, "status", None)`):

    - 412 — confirmation required (write gate; raised by the tool layer)
    - 424 — connector not configured (no base_url / api_key)
    - 401/403/404/4xx/5xx — the upstream WAHA HTTP status, passed through
    - 502 — host unreachable / timeout / unparseable (non-JSON) response
    """

    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ConfirmationRequiredError(WahaApiError):
    """A write tool was called without `confirm=true`.

    No side-effect is performed — the host LLM must re-call with
    `confirm=true` (confirm-then-execute, `KB § PATTERNS/llm-bot-security.md`).
    """

    def __init__(self, action: str):
        super().__init__(
            f"'{action}' is a write action. Re-call with confirm=true to "
            f"perform it. NO side-effect was performed.",
            status=412,
        )


def normalize_base_url(raw: str) -> str:
    """Return the instance root with no trailing slash (WAHA has no
    `/api/v1` prefix — paths are absolute)."""
    return (raw or "").rstrip("/")


def request_json(
    method: str,
    path: str,
    *,
    base_url: str,
    api_key: str,
    params: Optional[dict] = None,
    body: Optional[object] = None,
    timeout: float = 20.0,
    require_auth: bool = True,
) -> object:
    """Call `<base><path>` and return parsed JSON.

    `require_auth=False` for `/ping` (the one unauthenticated endpoint —
    lets `connection_status` distinguish "host down" from "key wrong").
    Missing base_url, or missing api_key when `require_auth`, is the
    connector-not-configured signal (424). Raises `WahaApiError` (typed
    `status`) on ANY failure — never a partial/fabricated success.
    """
    if not base_url or (require_auth and not api_key):
        raise WahaApiError(
            "WAHA connector not configured — set WAHA_BASE_URL and "
            "WAHA_API_KEY in mcp/waha/.env (or the environment).",
            status=424,
        )
    url = f"{normalize_base_url(base_url)}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url = f"{url}?{urllib.parse.urlencode(clean)}"

    data: Optional[bytes] = None
    headers = {"Accept": "application/json"}
    if api_key:
        headers["X-Api-Key"] = api_key
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
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001 — body read is best-effort context
            detail = ""
        raise WahaApiError(
            f"WAHA API {method.upper()} {path} → HTTP {e.code}"
            + (f": {detail}" if detail else ""),
            status=e.code,
        ) from e
    except urllib.error.URLError as e:
        raise WahaApiError(
            f"WAHA host unreachable for {method.upper()} {path}: {e.reason}",
            status=502,
        ) from e
    except TimeoutError as e:
        raise WahaApiError(
            f"WAHA API {method.upper()} {path} timed out after {timeout}s",
            status=502,
        ) from e

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise WahaApiError(
            f"WAHA API {method.upper()} {path} returned non-JSON output",
            status=502,
        ) from e


__all__ = [
    "request_json",
    "normalize_base_url",
    "WahaApiError",
    "ConfirmationRequiredError",
]
