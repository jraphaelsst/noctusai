"""`ImovelWebLead` → the unified-lead payload a product's lead service expects.

Pure: no DB, no client, no IO. Mirrors social-wiring's
`meta_ingest_service.map_meta_lead_to_lead_payload`, including its refusal
to invent a `data_entrada`.

---
**DRY note — this module is a deliberate fork of `olx/normalizers.py`, at N=2.**

The EN2 body looks near-identical to the Grupo OLX payload, and that is the
trap. Six differences land exactly where a shared abstraction would need
parameters: the dedup key is a different *concept* (delivery vs lead);
`leadOrigin` semantics invert (never-names-the-portal vs always-does); a
missing listing code means opposite things (4xx requeue vs 200); field names
are configuration here and fixed there; CPF is a whole LGPD class OLX lacks;
and a pull API changes the durability architecture, not just the parser.

The genuinely shared thing is the OUTPUT shape — the dict `create_lead`
accepts — which is already shared and already tested twice.

**Lift trigger:** the third portal receiver, OR the first commit that has to
change both `olx/normalizers.py` and this file for the same reason.
---
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from .types import ImovelWebLead

logger = logging.getLogger(__name__)

#: The STABLE `leads.external_source` for this feed — the *pipe*, never the
#: portal. It is half of `uq_sw_leads_org_external_lead`, so it must not vary
#: with the payload: if it tracked `leadOrigin`, the same `eventId`
#: re-delivered with a changed or absent `leadOrigin` would insert a SECOND
#: row and the unique index would not notice.
IMOVELWEB_PIPE = "imovelweb"

#: Fallback `lead_sources` slug. Already exists in social-wiring's
#: `leads/seed_data.py` with five raw-label aliases — do not mint a new one.
IMOVELWEB_DEFAULT_SOURCE_SLUG = "imovel-web"

#: `leadOrigin` → canonical `lead_sources` slug. Per-portal attribution is
#: HONEST here, unlike the OLX pipe, because the payload names the portal.
#:
#: `Wimoveis` is deliberately absent: it has no `lead_sources` row and no
#: observed BR traffic. It folds into `imovel-web` with the true value kept
#: in `origem_raw`. Minting a slug for a value nobody has seen would record
#: a guess in Portal ROI as if it were data.
IMOVELWEB_ORIGIN_SLUGS: dict[str, str] = {
    "Imovelweb": "imovel-web",
    "CasaMineira": "casa-mineira",
}


def resolve_source_slug(lead_origin: Optional[str]) -> str:
    """`leadOrigin` → the `lead_sources` slug to attribute the lead to.

    Unknown or absent values fall back to `imovel-web` with a WARNING
    rather than raising: attribution is a reporting concern, and losing a
    real lead over an unrecognised portal name would be a much worse
    trade. The raw value is preserved in `origem_raw` either way.
    """
    if not lead_origin:
        return IMOVELWEB_DEFAULT_SOURCE_SLUG
    slug = IMOVELWEB_ORIGIN_SLUGS.get(lead_origin.strip())
    if slug:
        return slug
    logger.warning(
        "imovelweb: unrecognised leadOrigin %r — attributing to %r and keeping "
        "the raw value in origem_raw. Add a mapping if this recurs.",
        lead_origin, IMOVELWEB_DEFAULT_SOURCE_SLUG,
    )
    return IMOVELWEB_DEFAULT_SOURCE_SLUG


def imovelweb_timestamp_to_date(value: Any) -> Optional[date]:
    """Vendor timestamp → its LOCAL date; `None` when unparseable.

    Two traps, both of which silently shift a measurable fraction of leads
    into the wrong day in Portal ROI:

    1. **Java's `Z` is an RFC-822 numeric offset** (`-0300`), not the
       literal character. `datetime.fromisoformat` only accepts that form
       from Python 3.11, so the offset is normalised to `-03:00` first
       rather than relying on the interpreter version.
    2. **The date is the SELLER's local date, not UTC.** A lead at 21:30
       BRT is the *previous* day in UTC. The safeguard is a negative one:
       we take `.date()` off the datetime **as sent** and never normalise
       to UTC first. `.date()` on an aware datetime already yields the
       date in that datetime's own offset, so an incoming `-03:00` gives
       the São Paulo date for free — but an `.astimezone(utc)` inserted
       anywhere above would silently break every evening lead. Do not add
       one. A naive value (no offset) is likewise read as sent, which for
       this vendor means BRT.

    Never guesses a date — an unparseable value is a named failure at the
    caller, not a silently-stamped `today()`.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None

    raw = value.strip()
    # `...Z` (literal, UTC) → an explicit offset fromisoformat accepts.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    else:
        # `+HHMM` / `-HHMM` → `+HH:MM`, for pre-3.11 compatibility.
        tail = raw[-5:]
        if len(raw) > 5 and tail[0] in "+-" and tail[1:].isdigit():
            raw = raw[:-5] + tail[:3] + ":" + tail[3:]

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None

    # Taken as sent, in both branches. No .astimezone() anywhere — see the
    # docstring: converting to UTC first is the one-day bug.
    return parsed.date()


def render_observacoes(lead: ImovelWebLead) -> Optional[str]:
    """The qualifying context, one `label: value` line each.

    The consumer's message first, then the signals a broker actually acts
    on. Returns `None` rather than an empty string so `observacoes IS NULL`
    keeps meaning "nothing to show".

    `identificationId` (CPF) is deliberately NOT rendered — see
    `imovelweb_lead_to_lead_payload`.
    """
    lines: list[str] = []
    if lead.message:
        lines.append(f"Mensagem: {lead.message}")
    contact_type = lead.contact_type
    if contact_type:
        lines.append(f"Tipo de contato: {contact_type}")
    elif lead.contact_type_id is not None:
        lines.append(f"Tipo de contato: {lead.contact_type_id} (não catalogado)")
    if lead.lead_origin:
        lines.append(f"Portal: {lead.lead_origin}")
    if lead.origin_listing_id:
        lines.append(f"Anúncio (portal): {lead.origin_listing_id}")
    if lead.internal_reference:
        lines.append(f"Código do anunciante: {lead.internal_reference}")
    if lead.development_code:
        lines.append(f"Lançamento: {lead.development_code}")
    return "\n".join(lines) or None


def imovelweb_lead_to_lead_payload(
    lead: ImovelWebLead,
    *,
    origem_source_id: str,
    external_source: str = IMOVELWEB_PIPE,
) -> dict[str, Any]:
    """One `ImovelWebLead` → the payload a product's `create_lead` expects.

    Raises `ValueError` when the timestamp is missing or unparseable:
    `data_entrada` is NOT NULL on `leads` and this module will not invent a
    date to satisfy a constraint. An un-ingestable lead is a named failure
    the caller surfaces, never a silent skip.

    Three deliberate omissions:

    * **`corretor_id`** — the payload carries no broker field, and guessing
      one would hand a real customer to the wrong person. An unassigned
      lead is honest; assignment is the product's decision, made where the
      org's roster is known.
    * **`identification_id` (CPF)** — a direct national identifier that no
      current feature consumes. Art. 6.III minimization: it is not
      projected, not stored in a typed column, and not logged. It survives
      only inside the ledger's `raw`, which is what makes that column
      personal data. → `KB § PATTERNS/security/lgpd.md`
    * **the portal slug as `external_source`** — see `IMOVELWEB_PIPE`.
      `external_source` is the pipe; `origem_id` is the portal. Conflating
      them turns a re-delivery into a duplicate row.
    """
    data_entrada = imovelweb_timestamp_to_date(lead.timestamp)
    if data_entrada is None:
        raise ValueError(
            f"imovelweb_lead_to_lead_payload: event {lead.event_id!r} has a "
            f"missing/unparseable timestamp ({lead.timestamp!r}) — data_entrada "
            "is NOT NULL on leads, refusing to guess"
        )

    origem_raw = " / ".join(
        p for p in (lead.lead_origin, lead.event_type, lead.contact_type) if p
    ) or None

    return {
        "external_source": external_source,
        # The DELIVERY id, not the contact id — one contact fans out to
        # several events, and keying on it would collapse distinct leads.
        "external_lead_id": lead.event_id,
        "data_entrada": data_entrada,
        "origem_id": origem_source_id,
        "origem_raw": origem_raw,
        # A portal enquiry is definitionally a first contact — there is no
        # "retorno" signal in this feed, so `novo` is explicit rather than
        # the `desconhecido` a create would otherwise default to.
        "tipo_lead": "novo",
        "cliente_nome": lead.name,
        "contato": lead.full_phone or lead.email,
        "codigo_imovel": lead.client_listing_id,
        "observacoes": render_observacoes(lead),
    }


__all__ = [
    "IMOVELWEB_DEFAULT_SOURCE_SLUG",
    "IMOVELWEB_ORIGIN_SLUGS",
    "IMOVELWEB_PIPE",
    "imovelweb_lead_to_lead_payload",
    "imovelweb_timestamp_to_date",
    "render_observacoes",
    "resolve_source_slug",
]
