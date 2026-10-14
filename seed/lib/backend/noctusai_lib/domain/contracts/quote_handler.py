"""`ContractQuoteAcceptHandler` -- the `QuoteAcceptHandler` that turns an accepted SERVICES quote into a DRAFT contract.

Wired by the HOST next to the quotes organ (the quotes organ imports neither this nor contracts). It is a thin adapter over
`create_contract_from_quote`, which is already idempotent per `quote_id` (`UNIQUE (org_id, source_quote_id)`), so a retried
conversion returns the SAME contract. The contract stays a draft: the operator reviews, renders and activates it (start / first due date default to the day
the customer accepted).

The contract total is the quote's total BY CONSTRUCTION: the header discount is spread over the lines (largest remainder,
integer cents) and a line that cannot keep its quantity (a fractional quantity, or any discount) becomes quantity 1 at its
net total -- the contract's `amount_cents` is derived from the lines, so any other mapping would silently bill more than the
customer accepted.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Sequence

from noctusai_lib.domain.quotes.handler import QuoteAcceptContext, QuoteConversion

from .config import ContractsConfig
from ._common import Scope, to_date, today
from .quotes import ContractFromQuote, QuoteLine, create_contract_from_quote


def spread_discount(totals: Sequence[int], discount_cents: int) -> list[int]:
    """`totals` reduced by `discount_cents`, proportionally, summing EXACTLY to `sum(totals) - discount` (largest remainder)."""
    gross = sum(totals)
    if discount_cents <= 0 or gross <= 0:
        return list(totals)
    discount_cents = min(discount_cents, gross)
    shares = [discount_cents * t // gross for t in totals]
    leftover = discount_cents - sum(shares)
    # hand the remaining cents to the lines with the largest fractional remainder (ties: the larger line, then the earlier)
    order = sorted(range(len(totals)), key=lambda i: (-(discount_cents * totals[i] % gross), -totals[i], i))
    for i in order[:leftover]:
        shares[i] += 1
    return [t - share for t, share in zip(totals, shares)]


def contract_lines(quote_lines: Sequence[Mapping[str, Any]], header_discount_cents: int) -> tuple[QuoteLine, ...]:
    """The contract lines for a quote's lines (`present_line` shape: `qty` float, `total_cents` = after line discount)."""
    nets = spread_discount([int(ln["total_cents"]) for ln in quote_lines], int(header_discount_cents or 0))
    out: list[QuoteLine] = []
    for ln, net in zip(quote_lines, nets):
        qty = float(ln["qty"])
        untouched = (
            qty == int(qty) and qty >= 1
            and not int(ln.get("discount_cents") or 0)
            and net == int(ln["total_cents"]) == int(qty) * int(ln["unit_price_cents"])
        )
        description = str(ln["description"])
        if untouched:
            out.append(QuoteLine(description=description, unit_price_cents=int(ln["unit_price_cents"]), quantity=int(qty), item_id=ln.get("item_id")))
        else:
            unit = str(ln.get("unit") or "UN")
            shown = f"{qty:g}".replace(".", ",")
            out.append(QuoteLine(description=f"{description} ({shown} {unit})", unit_price_cents=net, quantity=1, item_id=ln.get("item_id")))
    return tuple(out)


class ContractQuoteAcceptHandler:
    """`convert_to == "contract"` -> a draft contract, idempotent on the quote id."""

    def __init__(self, *, get_db: Callable[[], Any], cfg: ContractsConfig) -> None:
        self._get_db = get_db
        self._cfg = cfg

    def handle(self, ctx: QuoteAcceptContext) -> Optional[QuoteConversion]:
        quote = ctx.quote
        party = quote.get("party") or {}
        lines = contract_lines(ctx.lines, int(quote.get("discount_cents") or 0))
        title = (quote.get("title") or "").strip() or f"Orçamento {quote.get('number')}"
        # A draft needs a first due date: the day the customer accepted (the operator adjusts it before activating).
        first_day = to_date(ctx.acceptance.get("decided_at")) or today()
        request = ContractFromQuote(
            quote_id=str(quote["id"]),
            title=title,
            lines=lines,
            party_id=str(quote["party_id"]) if quote.get("party_id") else None,
            party_name=party.get("legal_name"),
            first_due_date=first_day,
            start_date=first_day,
            notes=quote.get("notes"),
        )
        contract, created = create_contract_from_quote(Scope(self._get_db(), self._cfg, str(ctx.org_id)), request)
        return QuoteConversion(kind="contract", ref=str(contract["id"]), detail={"created": created})


__all__ = ["ContractQuoteAcceptHandler", "contract_lines", "spread_discount"]
