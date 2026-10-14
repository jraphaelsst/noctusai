"""The PUBLIC view of a quote -- what the customer behind the signed link sees (and nothing more).

Allow-list, never a deny-list: the public dict is BUILT from named fields. It carries the offer itself (number,
version, title, validity, lines, money, notes, terms), the customer's display NAME and the seller's display name.
It never carries: the party's document / e-mail / phones / address, internal ids (party, item, org, creator),
who sent it or to what address, rejection of other versions, conversion or signature internals, or events.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from ._common import Scope, to_date
from .decisions import consent_text, get_acceptance
from .delivery import IssuerResolver, issuer_name
from .errors import bad_link
from .quotes import expire_if_due, get_party, get_row, quote_lines, record_event, transition
from .types import EventKind, OPEN_STATUSES, QuoteStatus

_QUOTES = "quotes"


def present_public(s: Scope, row: Mapping[str, Any], lines: list[Mapping[str, Any]], *, party_name: str, issuer: str,
                   acceptance: Optional[Mapping[str, Any]]) -> dict:
    open_ = row["status"] in OPEN_STATUSES and bool(row.get("is_current"))
    decision = None
    if acceptance is not None:
        decision = {"decision": acceptance["decision"], "decided_at": acceptance["decided_at"]}
    day = to_date(row.get("valid_until"))
    return {
        "number": row["number"],
        "version": row["version"],
        "title": row.get("title"),
        "status": row["status"],
        "currency": row.get("currency"),
        "valid_until": day.isoformat() if day else None,
        "notes": row.get("notes"),
        "terms": row.get("terms"),
        "subtotal_cents": row["subtotal_cents"],
        "discount_cents": row["discount_cents"],
        "total_cents": row["total_cents"],
        "party_name": party_name,
        "issuer_name": issuer,
        "lines": [
            {
                "position": int(ln.get("position") or 0), "description": ln["description"], "unit": ln.get("unit"),
                "qty": float(ln["qty"]), "unit_price_cents": ln["unit_price_cents"],
                "discount_cents": ln["discount_cents"], "total_cents": ln["total_cents"],
            }
            for ln in lines
        ],
        "can_decide": open_,
        "decision": decision,
        # The sentence is server-authored so what the page shows is what the acceptance row stores.
        "consent_template": consent_text(row, "{name}") if open_ else None,
    }


def public_quote(s: Scope, quote_id: Any, *, issuer: Optional[IssuerResolver] = None, mark_viewed: bool = False) -> dict:
    """The allow-listed view for `quote_id` (already proven by the token). `mark_viewed` flips `sent -> viewed` once."""
    row = expire_if_due(s, get_row(s, quote_id))
    if row["status"] == QuoteStatus.DRAFT.value:
        raise bad_link()  # a draft was never offered: the link cannot exist yet (same answer as any bad token)
    if mark_viewed and row["status"] == QuoteStatus.SENT.value and row.get("is_current"):
        viewed = transition(s, row, QuoteStatus.VIEWED.value, expect=[QuoteStatus.SENT.value], extra={"viewed_at": _now()})
        if viewed is not None:
            record_event(s, row["id"], EventKind.VIEWED, from_status="sent", to_status="viewed", detail={"channel": "public_link"})
            row = viewed
    party = get_party(s, row["party_id"]) or {}
    acceptance = get_acceptance(s, row["id"]) if row["status"] in (QuoteStatus.ACCEPTED.value, QuoteStatus.REJECTED.value) else None
    return present_public(
        s, row, quote_lines(s, row["id"]), party_name=str(party.get("legal_name") or ""),
        issuer=issuer_name(issuer, s.org_id), acceptance=acceptance,
    )


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


__all__ = ["present_public", "public_quote"]
