"""`OlxLead` → the unified-lead payload a product's lead service expects.

Pure: no DB, no client, no IO. Mirrors social-wiring's
`meta_ingest_service.map_meta_lead_to_lead_payload`, including its
refusal to invent a `data_entrada`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from .types import OlxLead

#: The canonical `lead_sources` slug this feed attributes to. ONE slug for
#: the whole Grupo OLX pipe, deliberately: the payload does not name the
#: portal, so splitting into `zap` / `viva-real` / `imovel-web` here would
#: be a guess written into Portal ROI as if it were data.
OLX_SOURCE_SLUG = "grupo-olx"


def olx_timestamp_to_date(value: Any) -> Optional[date]:
    """ISO-8601 `timestamp` → its DATE part; `None` when unparseable.

    Handles the trailing `Z` (`fromisoformat` rejects it before 3.11) and
    a plain `YYYY-MM-DD`. Never guesses — an unparseable timestamp is a
    named failure at the caller, not a silently-stamped today().
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
    return None


def render_observacoes(lead: OlxLead) -> Optional[str]:
    """The qualifying context, one `label: value` line each.

    The consumer's message first, then the vendor's own signals that a
    broker actually acts on — how the lead was made (`leadType`), whether
    it is exclusive (`leadCerto`), and the IZI conversation link. Returns
    `None` rather than an empty string so `observacoes IS NULL` keeps
    meaning "nothing to show".
    """
    lines: list[str] = []
    if lead.message:
        lines.append(f"Mensagem: {lead.message}")
    if lead.lead_type:
        lines.append(f"Canal: {lead.lead_type}")
    if lead.temperature:
        lines.append(f"Temperatura: {lead.temperature}")
    if lead.transaction_type:
        lines.append(f"Transação: {lead.transaction_type}")
    if lead.origin_listing_id:
        lines.append(f"Anúncio (portal): {lead.origin_listing_id}")
    if lead.extra_data.get("leadCerto") is True:
        lines.append("Lead Certo: sim")
    izi = lead.extra_data.get("izi")
    if isinstance(izi, str) and izi.strip():
        lines.append(f"IZI: {izi.strip()}")
    return "\n".join(lines) or None


def olx_lead_to_lead_payload(
    lead: OlxLead,
    *,
    origem_source_id: str,
    external_source: str = OLX_SOURCE_SLUG,
) -> dict[str, Any]:
    """One `OlxLead` → the payload a product's `create_lead` expects.

    Raises `ValueError` when `timestamp` is missing or unparseable:
    `data_entrada` is NOT NULL on `leads` and this module will not invent
    a date to satisfy a constraint. An un-ingestable lead is a named
    failure the caller surfaces, never a silent skip.

    `corretor_id` is deliberately absent. The OLX payload carries no
    broker field at all, and guessing one from free text would assign a
    real customer to the wrong person — an unassigned lead is honest.
    Round-robin or rule-based assignment is the product's decision, made
    where the org's roster is known, not here.
    """
    data_entrada = olx_timestamp_to_date(lead.timestamp)
    if data_entrada is None:
        raise ValueError(
            f"olx_lead_to_lead_payload: lead {lead.origin_lead_id!r} has a "
            f"missing/unparseable timestamp ({lead.timestamp!r}) — data_entrada "
            "is NOT NULL on leads, refusing to guess"
        )

    return {
        "external_source": external_source,
        "external_lead_id": lead.origin_lead_id,
        "data_entrada": data_entrada,
        "origem_id": origem_source_id,
        # Provenance that survives the join: which pipe, which channel.
        "origem_raw": " / ".join(p for p in (lead.lead_origin, lead.lead_type) if p) or None,
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
    "OLX_SOURCE_SLUG",
    "olx_lead_to_lead_payload",
    "olx_timestamp_to_date",
    "render_observacoes",
]
