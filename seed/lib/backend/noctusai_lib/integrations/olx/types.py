"""Value objects for the Grupo OLX (ZAP / VivaReal / ImovelWeb) lead feed.

One inbound delivery = one lead. `OlxLead` is the parsed shape; `raw`
carries the vendor body verbatim so nothing the parser did not model is
lost (the product persists `raw` in its ledger table).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: `extraData.leadType` — the channel the consumer used. Documented set as
#: of 2026-08-17; an unknown value is carried through, never rejected (a
#: new channel must not 4xx a real lead into OLX's retry queue).
OLX_LEAD_TYPES: tuple[str, ...] = (
    "CLICK_SCHEDULE",
    "CLICK_WHATSAPP",
    "CONTACT_CHAT",
    "CONTACT_FORM",
    "PHONE_VIEW",
    "VISIT_REQUEST",
)

#: Vendor-assigned lead quality. Portuguese, accented — the wire values.
OLX_TEMPERATURES: tuple[str, ...] = ("Baixa", "Média", "Alta")

OLX_TRANSACTION_TYPES: tuple[str, ...] = ("RENT", "SELL")

#: `leadOrigin` values seen in the vendor docs. `Grupo OLX` is the normal
#: listing lead; `MCMV_OLX` is a Minha-Casa-Minha-Vida simulation lead,
#: which carries NEITHER `originListingId` NOR `clientListingId`.
OLX_LEAD_ORIGIN_STANDARD = "Grupo OLX"
OLX_LEAD_ORIGIN_MCMV = "MCMV_OLX"


@dataclass(frozen=True)
class OlxLead:
    """One lead as delivered by the Grupo OLX webhook.

    `origin_lead_id` is the vendor's own id and the ONLY dedup key that
    means anything: OLX retries up to 3 times and stores failures for 14
    days, so the same lead legitimately arrives more than once.

    `client_listing_id` is OUR listing id (the one we published in the
    feed), `origin_listing_id` is theirs. Both are absent on MCMV leads —
    see `is_mcmv`.
    """

    origin_lead_id: str
    lead_origin: str
    timestamp: str
    name: Optional[str] = None
    email: Optional[str] = None
    ddd: Optional[str] = None
    phone: Optional[str] = None
    phone_number: Optional[str] = None
    message: Optional[str] = None
    temperature: Optional[str] = None
    transaction_type: Optional[str] = None
    client_listing_id: Optional[str] = None
    origin_listing_id: Optional[str] = None
    lead_type: Optional[str] = None
    extra_data: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_mcmv(self) -> bool:
        """MCMV leads are not tied to a listing, so the missing
        `clientListingId` is CORRECT for them — the receiver must not 4xx
        one back into OLX's retry queue for a field it will never send."""
        return self.lead_origin == OLX_LEAD_ORIGIN_MCMV

    @property
    def full_phone(self) -> Optional[str]:
        """`phoneNumber` when the vendor sent it, else `ddd` + `phone`.

        The vendor marks `phoneNumber` deprecated but still sends it;
        preferring it costs nothing and survives the day they stop
        splitting the area code. Digits only — no formatting invented
        here, canonicalization is the consumer's E.164 step.
        """
        if self.phone_number:
            return self.phone_number.strip() or None
        parts = [p.strip() for p in (self.ddd, self.phone) if p and p.strip()]
        return "".join(parts) or None


__all__ = [
    "OLX_LEAD_ORIGIN_MCMV",
    "OLX_LEAD_ORIGIN_STANDARD",
    "OLX_LEAD_TYPES",
    "OLX_TEMPERATURES",
    "OLX_TRANSACTION_TYPES",
    "OlxLead",
]
