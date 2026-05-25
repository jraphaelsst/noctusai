"""WAHA HTTP API runner — the external-service seam for this connector.

Every `waha.*` tool talks to the WAHA instance *through the operator's
`X-Api-Key`*. `request_json` is the single HTTP boundary; the urllib
mechanics are delegated to the shared `_kit.transport.request_json` seam
(kit-connector-boilerplate-consolidation). This wrapper keeps WAHA's own
`WahaApiError` type, the 424 not-configured gate, the `require_auth`
unauthenticated-`/ping` path, and the absolute-path base-URL normalizer.

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

from typing import Optional

from _kit.errors import confirmation_required_message
from _kit.transport import request_json as _http_request_json


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
        super().__init__(confirmation_required_message(action), status=412)


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
    # Delegate the urllib mechanics to the shared seam; WAHA keeps its own
    # absolute-path base-URL normalizer + WahaApiError type + the 424 gate
    # above. X-Api-Key is sent whenever present (incl. /ping when the key is
    # configured); `require_auth` only governs the 424 gate, not the header.
    url = f"{normalize_base_url(base_url)}{path}"
    return _http_request_json(
        method,
        url,
        auth_header=("X-Api-Key", api_key) if api_key else None,
        params=params,
        body=body,
        timeout=timeout,
        error_cls=WahaApiError,
        empty_result={},
        label=f"WAHA API {method.upper()} {path}",
    )


__all__ = [
    "request_json",
    "normalize_base_url",
    "WahaApiError",
    "ConfirmationRequiredError",
]
