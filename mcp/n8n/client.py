"""Shared `N8nClient` dependency-injection seam for every `n8n.*` tool.

Every `n8n.workflow.*` / `n8n.tag.*` / `n8n.execution.*` /
`n8n.credential.*` / `n8n.diagnostics.*` tool builds its client through
`get_client()` — a single settings-resolved seam (the FastAPI-dep-
factory module-slot convention: a private override slot, default
`None`, populated by an explicit `configure_client(...)` call).

Connector-side design choice: unlike
`noctusai_lib.integrations.n8n.get_n8n_client()`'s own "no api_key →
Fake" default (the right shape for OTHER seed consumers), THIS
connector requires explicit configuration — `get_client()` raises the
typed 424 (`api.require_configured`) when unconfigured, rather than
silently degrading to the seed's `FakeN8nClient`. An operator running
MCP tools against an unconfigured instance sees a loud, never-faked
signal instead of fabricated Fake data. See `api.py`'s module
docstring for the full rationale.

**Test seam (dependency injection, NOT monkeypatching).**
`configure_client(FakeN8nClient())` or
`configure_client(HttpxN8nClient(..., transport=httpx.MockTransport(...)))`
lets a test exercise the REAL handler path — confirm-gate + client call
+ typed-error mapping + MCP Out shaping — without a network round-trip.
Mirrors `mcp/google/tools/youtube.py`'s `configure_upload_client`
(`:76-94`, which lets a test "exercise the REAL handler path — gate +
OAuth-check + audit + shaping").
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.integrations.n8n import N8nClient, get_n8n_client

from . import api
from .settings import get_settings

# Test-only override slot — default None ⇒ production path. Populated by
# `configure_client(...)`, mirroring the module-level dep-factory slot
# convention used across the codebase.
_client_override: Optional[N8nClient] = None


def configure_client(client: Optional[N8nClient]) -> None:
    """Inject the `N8nClient` every `n8n.*` tool builds through (tests
    only). Pass `None` to restore the production path (settings-
    resolved, 424-gated when unconfigured)."""
    global _client_override
    _client_override = client


def get_client() -> N8nClient:
    """Return the active `N8nClient`.

    The DI override when set (tests); otherwise the settings-resolved
    client — raises the typed 424 (`api.N8nApiError`, via
    `api.require_configured`) when `N8N_BASE_URL`/`N8N_API_KEY` are
    unset. See the module docstring for why this connector is
    stricter than the seed factory's own "no api_key → Fake" default.
    """
    if _client_override is not None:
        return _client_override
    s = get_settings()
    api.require_configured(s)
    return get_n8n_client(base_url=s.base_url, api_key=s.api_key, timeout=s.timeout_seconds)


__all__ = ["configure_client", "get_client"]
