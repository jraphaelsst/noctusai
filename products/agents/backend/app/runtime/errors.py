"""Runtime-layer error types (contract §E.9).

Sibling of ``app.stores.errors`` — that module owns store-shaped failures
(``NotFound``, ``Conflict``, ``AlreadyDecided``, ``TurnInProgress``); this
module owns the one failure that is a RUNTIME concept, not a store one:
an approval decision arriving for a request no live process is waiting on.
"""
from __future__ import annotations


class Orphaned(Exception):
    """``ApprovalBroker.resolve`` raises this when the approval row is still
    ``pendente`` in the store, but no live in-process future is waiting on
    it in THIS process — the process that requested it died or restarted
    before a human decided (contract §E.2: 409 ``orphaned``).

    Distinct from :class:`app.stores.errors.NotFound` (the row doesn't
    exist / wrong org) and :class:`app.stores.errors.AlreadyDecided` (the
    row is already settled) — this is "the row is real and still pending,
    but nothing is listening for the answer any more."
    """


# ── Provider-neutral runtime (Lais A1) — typed failures a CALLER maps ───────
#
# `LlmToolRuntime` never raises a bare vendor/seed exception across its
# boundary: the seed's `LLMNotConfigured` / `LLMBudgetExceeded` / `LLMAPIError`
# are translated to these, each carrying the HTTP status + `code` the channel
# turn API (contract §3.1) and the studio conversation route answer with. A
# caller catches `LlmRuntimeError` and uses `.http_status` / `.code` / `.headers`
# — one mapping, in one place.


class LlmRuntimeError(Exception):
    """Base: ``http_status`` + ``code`` (+ ``headers``) are the API answer."""

    http_status: int = 500
    code: str = "llm_error"

    def __init__(self, detail: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.headers = dict(headers or {})


class LlmNotConfiguredError(LlmRuntimeError):
    """No provider key in THIS org's settings (B1 — never a platform/env/
    other-tenant fallback). Contract §3.1: 424 ``llm_not_configured``."""

    http_status = 424
    code = "llm_not_configured"

    def __init__(self, provider: str) -> None:
        super().__init__(f"Chave do provedor ({provider}) ausente para esta organização.")
        self.provider = provider


class LlmCapacityError(LlmRuntimeError):
    """The org's LLM budget is exhausted, or every concurrent-turn slot is
    busy. Contract §3.1: 429 ``capacidade`` + ``Retry-After``."""

    http_status = 429
    code = "capacidade"

    def __init__(self, detail: str, *, retry_after_seconds: int = 10) -> None:
        super().__init__(detail, headers={"Retry-After": str(retry_after_seconds)})
        self.retry_after_seconds = retry_after_seconds


class LlmUpstreamError(LlmRuntimeError):
    """The provider failed (after the seed's retries) or cannot serve tool
    calling. Contract §3.1: 502 ``llm_upstream``. ``detail`` is for logs —
    a lead-facing surface never shows it (§10.1 L2)."""

    http_status = 502
    code = "llm_upstream"
