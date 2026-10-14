"""The convert-on-accept SEAM -- `QuoteAcceptHandler`.

When a quote is accepted the organ records the acceptance, flips the status and then calls the host's handler
ONCE with everything it needs; the handler turns the accepted quote into a downstream record:

    convert_to == "order"     -> a commerce order      (a quote of goods)
    convert_to == "contract"  -> a contract            (a quote of services)
    convert_to == "none"      -> the organ never calls the handler

The commerce-order and contract handlers live with their organs and are wired by the HOST (`QuotesHandlers`);
this organ imports neither. The default is `NoopQuoteAcceptHandler` (returns `None` => conversion `skipped`,
retryable with `POST /{id}/convert` once a real handler is wired); `FakeQuoteAcceptHandler` records calls for tests.

Handler contract:
* **Idempotent on `quote["id"]`.** It can run twice (a retry after a crash, an operator re-running `convert`):
  it must return the SAME downstream record, never create a second one. Key your insert on the quote id.
* **Synchronous, raising on failure.** An exception marks the conversion `failed` (message kept, quote stays
  `accepted` -- the customer's acceptance is already recorded and is never rolled back by a downstream error).
* Return `QuoteConversion(kind, ref)` -- `ref` is the downstream id (order id / contract id) as text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class QuoteConversion:
    """What the handler made: `kind` ("order" / "contract" / a host-specific word) + the downstream `ref`."""

    kind: str
    ref: str
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class QuoteAcceptContext:
    """Everything a handler is given. Plain data -- no db handle, so a handler cannot bypass org scoping."""

    org_id: str
    quote: Mapping[str, Any]          # the presented quote (money in cents, `lines` attached)
    lines: tuple[Mapping[str, Any], ...]
    acceptance: Mapping[str, Any]     # the consent record (name, channel, decided_at, content_sha256)
    convert_to: str                   # "order" | "contract"


@runtime_checkable
class QuoteAcceptHandler(Protocol):
    def handle(self, ctx: QuoteAcceptContext) -> Optional[QuoteConversion]:
        """Create (idempotently) the downstream record. `None` = "I did nothing" (-> conversion `skipped`)."""
        ...


class NoopQuoteAcceptHandler:
    """The default: converts nothing (every accepted quote ends `conversion_status = skipped`)."""

    def handle(self, ctx: QuoteAcceptContext) -> Optional[QuoteConversion]:
        return None


class FakeQuoteAcceptHandler:
    """Records every call on `.calls`; returns a deterministic ref per quote (idempotent by construction).

    `raises` makes it fail (to exercise the `failed` + retry path); set it back to `None` to let the retry succeed.
    """

    def __init__(self, *, raises: Optional[BaseException] = None) -> None:
        self.calls: list[QuoteAcceptContext] = []
        self.raises = raises

    def handle(self, ctx: QuoteAcceptContext) -> Optional[QuoteConversion]:
        self.calls.append(ctx)
        if self.raises is not None:
            raise self.raises
        return QuoteConversion(kind=ctx.convert_to, ref=f"fake-{ctx.convert_to}-{ctx.quote['id']}")


class RoutingQuoteAcceptHandler:
    """Routes an accepted quote to the handler of its `convert_to` (`{"order": ..., "contract": ...}`).

    A kind without a handler is "I did nothing" (`None` -> conversion `skipped`, retryable once wired) -- exactly the
    `NoopQuoteAcceptHandler` answer, so a host can wire only the conversions it supports."""

    def __init__(self, handlers: Mapping[str, QuoteAcceptHandler]) -> None:
        self._handlers = dict(handlers)

    def handle(self, ctx: QuoteAcceptContext) -> Optional[QuoteConversion]:
        handler = self._handlers.get(ctx.convert_to)
        return handler.handle(ctx) if handler is not None else None


__all__ = ["FakeQuoteAcceptHandler", "NoopQuoteAcceptHandler", "QuoteAcceptContext", "QuoteAcceptHandler", "QuoteConversion", "RoutingQuoteAcceptHandler"]
