"""Trello API runner — the external-service seam for the live tools.

Every `trello.boards.*` / `trello.lists.*` / `trello.cards.*` /
`trello.checklists.*` / `trello.labels.*` / `trello.actions.*` tool that
makes a real HTTP call goes through `request_json` here. The urllib
mechanics are delegated to the shared `_kit.transport.request_json` seam
(kit-connector-boilerplate-consolidation); what stays connector-side is
Trello's own `TrelloApiError` type, the 424 not-configured gate, and the
**query-param** auth injection (`key`/`token` — NOT a header, unlike
every other connector in this repo; see `settings.py`'s module docstring).

**Test seam.** Trello is an external service, so tests
`unittest.mock.patch("trello.api.request_json", ...)` to feed canned
payloads without a network call — sanctioned by CLAUDE.md §1
("monkeypatching ... for external services ... is fine"). The
header/transport-shape tests patch the shared boundary
`_kit.transport.urlopen`. Our own code is never patched.

**Gated-capability honesty** (CLAUDE.md §1). No `key`/`token`, an
unreachable host, or an upstream non-2xx is a typed, never-faked
signal: tools return a `TrelloApiError` envelope (status carried), and
`trello.diagnostics.connection_status` reports `configured=false` /
`reachable=false` / `authenticated=false`. We never fabricate success.

No connector-side HTTP for a seed adapter to share with — this
connector is deliberately self-contained (`settings.py`'s module
docstring; `mcp/trello/README.md` § Architecture).
"""
from __future__ import annotations

from typing import Optional

from _kit.errors import confirmation_required_message
from _kit.transport import request_json as _http_request_json


class TrelloApiError(Exception):
    """A Trello API call could not produce a real result.

    `status` feeds the connector-MCP typed-error contract
    (`_kit.errors.typed_error` reads `getattr(e, "status", None)`):

    - 412 — confirmation required (write gate; raised by the tool layer)
    - 424 — connector not configured (no `key`/`token`)
    - 401/403/404/4xx/5xx — the upstream Trello HTTP status, passed
      through (401 = bad key/token, 400 = malformed request — Trello is
      unusually terse on 400 bodies, often just the string "invalid
      value for id")
    - 502 — host unreachable / timeout / unparseable (non-JSON) response
    """

    def __init__(self, message: str, *, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ConfirmationRequiredError(TrelloApiError):
    """A write tool was called without `confirm=true`.

    No side-effect is performed — the host LLM must re-call with
    `confirm=true` (confirm-then-execute, `KB § PATTERNS/llm-bot-security.md`).
    """

    def __init__(self, action: str, effect: str = ""):
        super().__init__(
            confirmation_required_message(action, effect, noun="write action"),
            status=412,
        )


def normalize_base_url(raw: str) -> str:
    """Trim a trailing slash. Trello's host is fixed
    (`settings.DEFAULT_BASE_URL`); this only guards against a caller
    supplying a base_url with a stray trailing slash in tests."""
    return (raw or "").rstrip("/")


def require_configured(settings) -> None:
    """Gate every live-call tool. Raised BEFORE any network attempt."""
    if not settings.configured:
        raise TrelloApiError(
            "Trello connector not configured — set TRELLO_API_KEY and "
            "TRELLO_TOKEN in mcp/trello/.env (or the environment). Get a "
            "key at https://trello.com/app-key, then generate a token "
            "from the link on that same page.",
            status=424,
        )


def request_json(
    method: str,
    path: str,
    *,
    api_key: str,
    token: str,
    base_url: str = "",
    params: Optional[dict] = None,
    body: Optional[object] = None,
    timeout: float = 20.0,
) -> object:
    """Call `<base><path>?key=...&token=...` and return parsed JSON.

    `api_key`/`token` come from the connector settings (resolved by the
    tool layer via `require_configured`, which must run first). Trello
    authenticates via QUERY PARAMS, not a header — `key`/`token` are
    merged into `params` here rather than passed as `auth_header`, which
    is the one respect in which this wrapper differs from every sibling
    connector's `request_json`. Raises `TrelloApiError` (typed `status`)
    on ANY failure — never returns a partial or fabricated success.
    """
    merged_params = dict(params or {})
    merged_params["key"] = api_key
    merged_params["token"] = token
    url = f"{normalize_base_url(base_url)}{path}"
    return _http_request_json(
        method,
        url,
        auth_header=None,
        params=merged_params,
        body=body,
        timeout=timeout,
        error_cls=TrelloApiError,
        empty_result={},
        label=f"Trello API {method.upper()} {path}",
    )


__all__ = [
    "ConfirmationRequiredError",
    "TrelloApiError",
    "normalize_base_url",
    "require_configured",
    "request_json",
]
