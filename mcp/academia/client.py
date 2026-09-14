"""academia HTTP client — the transport seam every `academia.*` tool
calls through (CONTRACT §B).

Protocol + Fake + Real + factory, per `KB § PATTERNS/backend/
seed-fake-real-adapter.md`, applied at the connector-MCP scope: every
`academia.*` tool routes its HTTP call through `AcademiaApi.request(...)`,
which ALWAYS returns the tool-output envelope

    {"ok": true, **body}                                   — success
    {"ok": false, "error": {"status", "code", "detail"}}    — failure

and never raises. `HttpAcademiaApi` is the real adapter (httpx, Bearer,
30s timeout); `FakeAcademiaApi` is the deterministic in-memory adapter
tool-level tests dispatch against — it records every call
(`method`/`path`/`params`/`json_body`) so a test can assert the exact
wire shape a CONTRACT §C row requires without a network round-trip.

**Test seam (dependency injection, NOT monkeypatching).**
`configure_client(FakeAcademiaApi())` lets a test exercise the REAL
handler path (input validation → client call → envelope passthrough)
without a network call. Mirrors `mcp/n8n/client.py`'s
`configure_client`/`get_client` — a first-class module-level override
slot, not a patch of our own code.

**Gated-capability honesty** (CLAUDE.md §1). Missing config, an
unreachable host, or an upstream non-2xx is a typed, never-faked
signal — this module never fabricates or partially-returns a success.
The token is never logged: no log statement in this module ever
includes `settings.api_token` or the built `Authorization` header.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

import httpx

from .settings import AcademiaSettings, get_settings

logger = logging.getLogger(__name__)

#: CONTRACT §C build step 2 — "30s timeout".
DEFAULT_TIMEOUT_SECONDS = 30.0


@runtime_checkable
class AcademiaApi(Protocol):
    """Surface every `academia.*` tool calls through. Both
    `FakeAcademiaApi` and `HttpAcademiaApi` satisfy this Protocol
    naturally (`KB § PATTERNS/backend/seed-fake-real-adapter.md`)."""

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Issue one call to `<ACADEMIA_API_URL><path>`.

        ALWAYS returns the tool-output envelope
        (`{"ok": true, **body}` / `{"ok": false, "error": {...}}`) —
        never raises."""
        ...


def _not_configured_envelope() -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "status": 0,
            "code": "not_configured",
            "detail": (
                "academia connector not configured — set ACADEMIA_API_URL "
                "and ACADEMIA_API_TOKEN (mcp/academia/.env or the "
                "environment)."
            ),
        },
    }


def _unreachable_envelope(detail: str) -> dict[str, Any]:
    return {"ok": False, "error": {"status": 0, "code": "unreachable", "detail": detail}}


@dataclass
class HttpAcademiaApi:
    """Real adapter — httpx, `Authorization: Bearer <token>`, 30s
    timeout (CONTRACT §C build steps 1-2).

    Constructed from `AcademiaSettings`. Every call checks
    `settings.configured` first — an unconfigured connector never
    attempts a network call and never crashes at import/construction.
    """

    settings: AcademiaSettings

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not self.settings.configured:
            return _not_configured_envelope()

        url = f"{(self.settings.api_url or '').rstrip('/')}{path}"
        headers = {"Authorization": f"Bearer {self.settings.api_token}"}
        timeout = self.settings.timeout_seconds or DEFAULT_TIMEOUT_SECONDS
        # httpx serializes a `None` param as an EMPTY query value
        # (`?a=`), not an omitted one — drop them here so every tool
        # module can pass its full optional-filter dict unfiltered.
        clean_params = {k: v for k, v in (params or {}).items() if v is not None} or None

        try:
            async with httpx.AsyncClient(timeout=timeout) as http_client:
                resp = await http_client.request(
                    method.upper(), url, params=clean_params, json=json_body, headers=headers,
                )
        except httpx.TimeoutException:
            logger.warning("academia API %s %s timed out after %ss", method.upper(), path, timeout)
            return _unreachable_envelope(f"{method.upper()} {path} timed out after {timeout}s")
        except httpx.HTTPError as exc:
            # Any other transport-level failure (connection refused, DNS,
            # TLS, …). `str(exc)` on httpx transport errors carries the
            # URL/reason, never request headers — the Authorization
            # header is never part of this message.
            logger.warning("academia API %s %s unreachable: %s", method.upper(), path, exc)
            return _unreachable_envelope(f"{method.upper()} {path} — host unreachable: {exc}")

        return self._envelope_from_response(resp, method, path)

    @staticmethod
    def _envelope_from_response(resp: "httpx.Response", method: str, path: str) -> dict[str, Any]:
        if resp.status_code < 400:
            if not resp.content:
                return {"ok": True}
            try:
                body = resp.json()
            except ValueError:
                return _unreachable_envelope(f"{method.upper()} {path} returned non-JSON output")
            if isinstance(body, dict):
                return {"ok": True, **body}
            return {"ok": True, "result": body}

        # Error path — use the server's error shape ({"detail","code"},
        # CONTRACT §0) when the body carries it; fall back to a generic
        # code + a status-line detail otherwise.
        code = "http_error"
        detail = f"{method.upper()} {path} -> HTTP {resp.status_code}"
        try:
            error_body = resp.json()
        except ValueError:
            error_body = None
        if isinstance(error_body, dict):
            code = error_body.get("code") or code
            detail = error_body.get("detail") or detail
        return {
            "ok": False,
            "error": {"status": resp.status_code, "code": code, "detail": detail},
        }


@dataclass
class FakeAcademiaApi:
    """Deterministic in-memory adapter.

    Tool-level tests script it with `set_response(method, path,
    envelope)` and assert against the recorded `calls` — the
    `{method, path, params, json_body}` shape CONTRACT §C requires per
    row. Unscripted calls return a generic empty-list success envelope
    so a test that only cares about the request shape doesn't also
    have to script the response."""

    _responses: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def set_response(self, method: str, path: str, envelope: dict[str, Any]) -> None:
        """Script the envelope returned for `(method, path)`. `envelope`
        is returned VERBATIM — pass the full `{"ok": ..., ...}` shape,
        including error envelopes for negative-path tests."""
        self._responses[(method.upper(), path)] = envelope

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {"method": method.upper(), "path": path, "params": params, "json_body": json_body}
        )
        envelope = self._responses.get((method.upper(), path))
        if envelope is not None:
            return envelope
        return {"ok": True, "items": [], "total": 0}


# Test-only override slot — default None ⇒ production path. Populated by
# `configure_client(...)`, mirroring `mcp/n8n/client.py`'s DI seam.
_client_override: Optional[AcademiaApi] = None


def configure_client(client: Optional[AcademiaApi]) -> None:
    """Inject the `AcademiaApi` every `academia.*` tool builds through
    (tests only). Pass `None` to restore the production path
    (settings-resolved `HttpAcademiaApi`)."""
    global _client_override
    _client_override = client


def get_client(settings: Optional[AcademiaSettings] = None) -> AcademiaApi:
    """Return the active `AcademiaApi`.

    The DI override when set (tests); otherwise `HttpAcademiaApi`
    resolved from settings. Deliberately does NOT auto-select a Fake
    when unconfigured — CONTRACT §C build step 1 requires every tool to
    surface the typed `not_configured` envelope, which is
    `HttpAcademiaApi.request`'s own first check, not a client-selection
    decision."""
    if _client_override is not None:
        return _client_override
    return HttpAcademiaApi(settings or get_settings())


__all__ = [
    "AcademiaApi",
    "HttpAcademiaApi",
    "FakeAcademiaApi",
    "configure_client",
    "get_client",
    "DEFAULT_TIMEOUT_SECONDS",
]
