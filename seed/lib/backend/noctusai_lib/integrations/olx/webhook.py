"""Pure parsing for the Grupo OLX lead webhook — zero IO, zero FastAPI.

Mirrors `integrations/meta/leadgen_webhook.py`: any product's router can
import these directly, and they are unit-testable without a request, a
client or a database.
"""

from __future__ import annotations

from typing import Any, Optional

from .types import OlxLead


def parse_olx_lead_webhook(payload: Any) -> Optional[OlxLead]:
    """One delivery body → one `OlxLead`, or `None` when unparseable.

    Returns `None` — never raises — for a non-dict body or one with no
    `originLeadId`. Without that id there is no dedup key, so the lead
    could not be stored idempotently even if the rest parsed; the caller
    persists the raw body and answers 4xx so OLX retries.

    Everything else is carried through as-is. In particular this does
    NOT reject an unknown `leadType`, `temperature` or `transactionType`:
    validation against the documented contract is
    `contract.validate_olx_lead_payload`'s job and is advisory. A parser
    that rejected a value the vendor added last week would 4xx real
    leads into a retry queue that discards them after 14 days.
    """
    if not isinstance(payload, dict):
        return None

    origin_lead_id = payload.get("originLeadId")
    if not isinstance(origin_lead_id, str) or not origin_lead_id.strip():
        return None

    extra_data = payload.get("extraData")
    if not isinstance(extra_data, dict):
        extra_data = {}

    lead_type = extra_data.get("leadType")
    if not isinstance(lead_type, str):
        lead_type = None

    return OlxLead(
        origin_lead_id=origin_lead_id.strip(),
        lead_origin=_str_or_empty(payload.get("leadOrigin")),
        timestamp=_str_or_empty(payload.get("timestamp")),
        name=_opt_str(payload.get("name")),
        email=_opt_str(payload.get("email")),
        ddd=_opt_str(payload.get("ddd")),
        phone=_opt_str(payload.get("phone")),
        phone_number=_opt_str(payload.get("phoneNumber")),
        message=_opt_str(payload.get("message")),
        temperature=_opt_str(payload.get("temperature")),
        transaction_type=_opt_str(payload.get("transactionType")),
        client_listing_id=_opt_str(payload.get("clientListingId")),
        origin_listing_id=_opt_str(payload.get("originListingId")),
        lead_type=lead_type,
        extra_data=extra_data,
        raw=payload,
    )


def _opt_str(value: Any) -> Optional[str]:
    """Coerce a scalar to a trimmed string; `None` for empty/absent.

    Numeric ids are coerced rather than dropped — a vendor that starts
    sending `originListingId` as an int must not silently lose the field.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _str_or_empty(value: Any) -> str:
    return _opt_str(value) or ""


__all__ = ["parse_olx_lead_webhook"]
