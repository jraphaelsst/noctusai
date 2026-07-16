"""n8n connector-MCP error contract + the not-configured gate.

`request_json` (the sync urllib HTTP seam) is GONE — every `n8n.*`
tool now builds an `N8nClient` through `client.get_client()` (the DI
seam, `mcp/n8n/client.py`) and awaits the seed's Protocol methods
directly (`HttpxN8nClient` / `FakeN8nClient`,
`seed/lib/backend/noctusai_lib/integrations/n8n/`). Those adapters own
the wire mechanics (endpoint paths, the `{data,nextCursor}` envelope,
the `X-N8N-API-KEY` header, the WAF User-Agent) AND the error taxonomy
(`N8nError` → `N8nAuthError`/`N8nNotFoundError`/`N8nRateLimitedError`/
`N8nRejectedError`/`N8nUnreachableError`) — a second connector-side copy
of either is the exact fork this module used to risk.

`normalize_base_url` is re-exported from `noctusai_lib.integrations.n8n`
(settings.py's `api_root` property depends on this exact name staying
importable from `n8n.api`).

What genuinely stays connector-side (the real, narrow boundary):
- `ConfirmationRequiredError`/412 — the MCP write-gate contract; a
  product API has its own authz, this is specific to the LLM-tool
  confirm-then-execute pattern.
- `require_configured` / the 424 not-configured gate — every tool
  (not just diagnostics) returns a typed 424 when `N8N_BASE_URL`/
  `N8N_API_KEY` are unset, rather than silently degrading to the
  seed's `FakeN8nClient`. This is a DELIBERATE connector-level choice,
  stricter than `get_n8n_client()`'s own "no api_key → Fake" default
  (the right shape for OTHER seed consumers, e.g. a product backend
  that wants graceful local-dev behavior) — an operator running MCP
  tools against an unconfigured n8n instance should see a loud 424,
  never fabricated Fake data. See `mcp/n8n/client.py`.
- `map_seed_error` — translates ANY adapter-layer failure (a seed
  `N8nError`, or an already-typed `N8nApiError` from `require_configured`/
  the confirm gate) into the uniform `N8nApiError` every tool Output
  wraps via `typed_error`.

**Test seam (dependency injection, NOT monkeypatching).**
`mcp/n8n/client.configure_client(FakeN8nClient())` or
`configure_client(HttpxN8nClient(..., transport=httpx.MockTransport(...)))`
lets a test exercise the REAL handler path — confirm-gate + client call
+ error mapping + MCP Out shaping — without a network round-trip.
Mirrors `mcp/google/tools/youtube.py`'s `configure_upload_client`
(`:76-94`). `mcp/n8n/api.py`'s OWN symbols (`N8nApiError`,
`require_configured`, `map_seed_error`) are never patched — they are
plain functions/classes exercised for real by every test.
"""
from __future__ import annotations

from typing import Optional

from _kit.errors import confirmation_required_message
from noctusai_lib.integrations.n8n import N8nError, normalize_base_url


class N8nApiError(Exception):
    """An n8n API call could not produce a real result.

    `status` feeds the connector-MCP typed-error contract
    (`_kit.errors.typed_error` reads `getattr(e, "status", None)`):

    - 412 — confirmation required (write gate; raised by the tool layer)
    - 424 — connector not configured (no base_url / api_key)
    - 401/403/404/409/429/4xx/5xx — the upstream/seed status, passed
      through via `map_seed_error`
    - 502 — host unreachable / timeout / unparseable (non-JSON)
      response — the seed's transport-failure signal (`status=0`)
      maps here
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


def require_configured(settings) -> None:
    """Raise the connector-not-configured signal (424) when
    `settings.configured` is False.

    Every `n8n.*` tool calls this (via `client.get_client()`) before
    building the seed client — the exact check `request_json` used to
    perform inline, now centralized so every tool keeps identical
    gated-capability-honesty behavior, not just
    `n8n.diagnostics.connection_status`.
    """
    if not settings.configured:
        raise N8nApiError(
            "n8n connector not configured — set N8N_BASE_URL and "
            "N8N_API_KEY in mcp/n8n/.env (or the environment).",
            status=424,
        )


def map_seed_error(exc: N8nApiError | N8nError) -> N8nApiError:
    """Translate any adapter-layer failure into `N8nApiError`.

    An already-typed `N8nApiError` (412 from the confirm gate, 424
    from `require_configured`) passes through unchanged. A seed
    `N8nError` (`N8nAuthError`/`N8nNotFoundError`/
    `N8nRateLimitedError`/`N8nRejectedError`/`N8nUnreachableError`/
    `N8nWorkflowNotRunnableError`) maps via its own `.status` — the
    REAL upstream HTTP code the seed adapter already carries.
    `status=0` (the seed's transport-failure signal — network/TLS/
    timeout/unparseable) maps to 502, the exact prior `request_json`
    contract ("502 — host unreachable / timeout / unparseable
    response").
    """
    if isinstance(exc, N8nApiError):
        return exc
    status = getattr(exc, "status", 0) or 502
    return N8nApiError(str(exc), status=status)


__all__ = [
    "normalize_base_url",
    "N8nApiError",
    "ConfirmationRequiredError",
    "require_configured",
    "map_seed_error",
]
