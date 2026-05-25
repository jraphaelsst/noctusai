"""n8n REST API runner — the external-service seam for this connector.

Every `n8n.*` tool talks to the self-hosted instance *through the
operator's public-API key*. `request_json` is the single HTTP boundary
(stdlib `urllib` — zero extra deps, the same "wrap the stdlib"
discipline `mcp/github` applies to `subprocess`).

**Test seam.** n8n is an external service, so tests
`unittest.mock.patch("n8n.api.request_json", ...)` to feed canned
payloads without a network call — sanctioned by CLAUDE.md §1
("monkeypatching ... for external services ... is fine"; this is the
same class). Our own code is never patched.

**Gated-capability honesty** (CLAUDE.md §1). No base-URL / API-key,
an unreachable host, or an upstream non-2xx is a typed, never-faked
signal: tools return an `N8nApiError` envelope (status carried), and
`n8n.diagnostics.connection_status` reports `configured=false` /
`reachable=false`. We never fabricate a success.
"""
from __future__ import annotations

from typing import Optional

from _kit.errors import confirmation_required_message
from _kit.transport import request_json as _http_request_json


class N8nApiError(Exception):
    """An n8n API call could not produce a real result.

    `status` feeds the connector-MCP typed-error contract
    (`_kit.errors.typed_error` reads `getattr(e, "status", None)`):

    - 412 — confirmation required (write gate; raised by the tool layer)
    - 424 — connector not configured (no base_url / api_key)
    - 401/403/404/4xx/5xx — the upstream n8n HTTP status, passed through
    - 502 — host unreachable / timeout / unparseable (non-JSON) response
    """

    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ConfirmationRequiredError(N8nApiError):
    """A write tool was called without `confirm=true`.

    No side-effect is performed — the host LLM must re-call with
    `confirm=true` (confirm-then-execute, `KB § PATTERNS/llm-bot-security.md`).
    """

    def __init__(self, action: str):
        super().__init__(confirmation_required_message(action), status=412)


def normalize_base_url(raw: str) -> str:
    """Return the API root ending in `/api/v1`, no trailing slash.

    Accepts either the instance root (`https://n8n.example.com`) or an
    already-suffixed URL (`https://n8n.example.com/api/v1`) — both
    normalize to the same value so the operator can't get it subtly
    wrong in `.env`.
    """
    base = (raw or "").rstrip("/")
    if not base:
        return ""
    if base.endswith("/api/v1"):
        return base
    return f"{base}/api/v1"


def request_json(
    method: str,
    path: str,
    *,
    base_url: str,
    api_key: str,
    params: Optional[dict] = None,
    body: Optional[object] = None,
    timeout: float = 20.0,
) -> object:
    """Call `<base>/api/v1<path>` and return parsed JSON.

    `base_url` / `api_key` come from the connector settings (resolved by
    the tool layer). Missing either is the connector-not-configured
    signal (424). Raises `N8nApiError` (typed `status`) on ANY failure —
    never returns a partial or fabricated success.
    """
    if not base_url or not api_key:
        raise N8nApiError(
            "n8n connector not configured — set N8N_BASE_URL and "
            "N8N_API_KEY in mcp/n8n/.env (or the environment).",
            status=424,
        )
    # Delegate the urllib mechanics to the shared seam; n8n keeps its own
    # /api/v1 base-URL normalization + N8nApiError type + the 424 not-configured
    # gate above. (kit-connector-boilerplate-consolidation Wave 2 pilot.)
    url = f"{normalize_base_url(base_url)}{path}"
    return _http_request_json(
        method,
        url,
        auth_header=("X-N8N-API-KEY", api_key),
        params=params,
        body=body,
        timeout=timeout,
        error_cls=N8nApiError,
        empty_result={},
        label=f"n8n API {method.upper()} {path}",
    )


__all__ = [
    "request_json",
    "normalize_base_url",
    "N8nApiError",
    "ConfirmationRequiredError",
]
