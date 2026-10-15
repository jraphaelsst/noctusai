"""
Inbound WhatsApp -> automation triggers.

Decision (conservative, 2026-10-15): an inbound message only drives automations
when its sender is a KNOWN lead of the connection's org (matched by phone).
Messages from unknown numbers are logged and dropped — we do NOT create leads
from arbitrary WhatsApp chatter (spam / customers / the owner's own contacts
would pollute the CRM). Lead creation stays an explicit act (form, API, Meta).

For a known lead, in order:
  1. `stop_on_reply`: running executions whose flow stops on reply are canceled
     (default ON, per the Orbity flow defaults); the rest get
     `context.lead_replied = true` so `branch`/`condition` steps can read it.
  2. `whatsapp_message_received` fires for every active flow of that trigger.
  3. `keyword_received` fires for flows whose `trigger_config.keyword` is
     contained (case-insensitive) in the message text.
Idempotent: the trigger key is the provider message id, so a re-delivered
webhook never starts a flow twice.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import UUID

from noctusai_lib.primitives.phone import phone_digits

from app.services.automation_service import AutomationService
from app.services.automation_triggers import disparar

logger = logging.getLogger(__name__)


def phone_candidates(raw: str | None) -> list[str]:
    """Stored-phone spellings that can match one WhatsApp number: the canonical
    digits plus the Brazilian mobile 9th-digit variant (12 <-> 13 digits)."""
    digits = phone_digits(raw)
    if not digits:
        return []
    out = [digits]
    if digits.startswith("55"):
        if len(digits) == 13 and digits[4] == "9":
            out.append(digits[:4] + digits[5:])
        elif len(digits) == 12 and digits[4] in "6789":
            out.append(digits[:4] + "9" + digits[4:])
    return out


def find_lead_by_phone(db: Any, org_id: str, raw_phone: str | None) -> dict[str, Any] | None:
    """Newest lead of the org whose phone matches. None when there is none."""
    candidates = phone_candidates(raw_phone)
    if not candidates:
        return None
    rows = (
        db.table("leads")
        .select("id, name, phone")
        .eq("org_id", org_id)
        .in_("phone", candidates)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data or []
    return rows[0] if rows else None


def register_reply(db: Any, org_id: str, lead_id: str) -> dict[str, int]:
    """Apply stop_on_reply / lead_replied to the lead's RUNNING executions."""
    svc = AutomationService(db, org_id=UUID(org_id))
    canceled = svc.stop_on_reply(lead_id)
    return {"canceled": canceled}


def process_inbound(db: Any, org_id: str, inbound: Any) -> dict[str, Any]:
    """Handle one parsed inbound message (sync; call off the event loop)."""
    if getattr(inbound, "group_id", None):
        return {"handled": False, "reason": "group"}
    lead = find_lead_by_phone(db, org_id, getattr(inbound, "from_phone", None))
    if not lead:
        logger.debug("orbity whatsapp inbound: remetente desconhecido org=%s — ignorado", org_id)
        return {"handled": False, "reason": "unknown_sender"}

    lead_id = str(lead["id"])
    text = str(getattr(inbound, "text", "") or "")
    message_key = getattr(inbound, "provider_message_id", None) or hashlib.sha256(
        f"{lead_id}|{text}".encode("utf-8")
    ).hexdigest()[:32]

    stopped = register_reply(db, org_id, lead_id)
    key = f"inbound:{message_key}"
    started = disparar(
        "whatsapp_message_received", org_id, lead_id=lead_id,
        payload={"text": text}, trigger_key=key, db=db,
    )
    started += disparar(
        "keyword_received", org_id, lead_id=lead_id,
        payload={"text": text}, trigger_key=key, db=db,
    )
    return {"handled": True, "lead_id": lead_id, "canceled": stopped["canceled"], "started": len(started)}
