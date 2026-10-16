"""Orbity's host side of the seed billing-reminders (dunning) organ.

The organ (``noctusai_lib.domain.finance.reminders``) owns rules, selection, the dedup-first ledger, retries and the
daily job. This module only supplies the three things it cannot know, as ``ReminderPorts``:

* ``resolve_contact`` -- WHO a receivable's reminder is about: the ``orbity.clients`` row the receivable's
  ``billing_charges`` sidecar points at (nome fantasia ``name``, Razão Social ``legal_name``, ``phone``), plus the gateway
  payment link (``invoice_url``) and PIX copia-e-cola (``pix_payload``) of that charge. A receivable with no client
  (a hand-keyed one) falls back to its counterparty name and has no phone, so the organ reports ``no_address_for_channel``
  instead of guessing.
* ``skip_reason`` -- the veto: an INACTIVATED client whose charge was not kept ("preservada") must not be dunned, and
  neither must a charge whose gateway cancel is pending / done.
* the WhatsApp channel -- the org's OWN saved line (``orbity.whatsapp_connections``, newest first; no ``purpose`` column
  yet, so every line counts as ``general``), sent through the BR 9th-digit-resolving path. Unlike the automation sender
  there is deliberately NO fallback to the static fleet ``WAHA_*`` line: a billing message must come from the org's number.
  No line => a loud ``failed`` log row ("sem linha de WhatsApp conectada"), never a silent skip.

Reminders stay OFF per org until an admin enables them (Financeiro > Lembretes); enabling seeds the default rules.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from noctusai_lib.domain.finance._common import Scope
from noctusai_lib.domain.finance.reminders import (
    ReminderContact,
    ReminderPorts,
    make_reminder_channel,
    make_waha_client_resolver,
)
from noctusai_lib.integrations.whatsapp import build_whatsapp_connection_store
from noctusai_lib.security.api_keys import EncryptionNotConfigured

logger = logging.getLogger(__name__)

CHARGES = "billing_charges"
CLIENTS = "clients"

SKIP_CLIENT_INACTIVE = "client_inactive"
SKIP_CHARGE_CANCELLED = "charge_cancelled"
#: ``billing_charges.gateway_cancel_status`` values meaning the gateway-side charge is (being) cancelled.
_CANCELLED_AT_GATEWAY = ("pending", "done")


def _first(resp: Any) -> Optional[dict]:
    rows = getattr(resp, "data", None) or []
    return dict(rows[0]) if rows else None


def load_charge_and_client(s: Scope, entry: Mapping[str, Any]) -> tuple[Optional[dict], Optional[dict]]:
    """The receivable's ``billing_charges`` row and its client (both org-scoped), either may be None."""
    charge = _first(s.db.table(CHARGES).select("*").eq("org_id", s.org_id).eq("entry_id", str(entry["id"])).limit(1).execute())
    client_id = (charge or {}).get("client_id")
    if not client_id:
        return charge, None
    client = _first(s.db.table(CLIENTS).select("*").eq("org_id", s.org_id).eq("id", str(client_id)).limit(1).execute())
    return charge, client


def resolve_contact(s: Scope, entry: Mapping[str, Any]) -> Optional[ReminderContact]:
    charge, client = load_charge_and_client(s, entry)
    if client is None:
        name = (entry.get("counterparty_name") or "").strip()
        if not name:
            return None
        return ReminderContact(nome=name)  # no phone => the organ skips it as `no_address_for_channel`
    fantasia = (client.get("name") or "").strip()
    razao = (client.get("legal_name") or "").strip() or fantasia
    return ReminderContact(
        nome=fantasia or razao,
        phone=(client.get("phone") or "").strip() or None,
        razao_social=razao or None,
        nome_fantasia=fantasia or None,
        link_pagamento=((charge or {}).get("invoice_url") or None),
        pix_copia_cola=((charge or {}).get("pix_payload") or None),
    )


def skip_reason(s: Scope, entry: Mapping[str, Any]) -> Optional[str]:
    charge, client = load_charge_and_client(s, entry)
    if charge and charge.get("gateway_cancel_status") in _CANCELLED_AT_GATEWAY:
        return SKIP_CHARGE_CANCELLED
    if client is not None and (client.get("inactivated_at") or client.get("active") is False):
        if not (charge or {}).get("preserved_after_deactivation"):
            return SKIP_CLIENT_INACTIVE
    return None


def _org_waha_client(org_id: str) -> Any:
    """``org_id -> WahaClient | None`` over the org's saved connections. A missing ``ENCRYPTION_KEY`` is "no usable line"."""
    from app.config import settings
    from app.dependencies import get_admin_client

    try:
        store = build_whatsapp_connection_store(get_admin_client(), encryption_key=settings.encryption_key, schema="orbity")
        return make_waha_client_resolver(store)(org_id)
    except EncryptionNotConfigured:
        logger.warning("orbity reminders: ENCRYPTION_KEY ausente — conexões WhatsApp ignoradas (org=%s)", org_id)
        return None


def build_reminder_ports(*, resolve_client: Any = None) -> ReminderPorts:
    """The ports the router (preview) AND the daily job share. ``resolve_client`` is the DI seam tests use."""
    return ReminderPorts(
        channels={"whatsapp": make_reminder_channel("whatsapp", resolve_client=resolve_client or _org_waha_client)},
        resolve_contact=resolve_contact,
        skip_reason=skip_reason,
    )


__all__ = ["SKIP_CHARGE_CANCELLED", "SKIP_CLIENT_INACTIVE", "build_reminder_ports", "load_charge_and_client", "resolve_contact", "skip_reason"]
