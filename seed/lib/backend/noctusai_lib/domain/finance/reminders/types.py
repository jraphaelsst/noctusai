"""Vocabulary + pure value types of the billing-reminder (dunning) organ."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_EMAIL = "email"
CHANNELS: tuple[str, ...] = (CHANNEL_WHATSAPP, CHANNEL_EMAIL)

#: log lifecycle. `pending` = claimed, send not yet resolved (a crash leaves it; it is NEVER auto-resent --
#: the message may have gone out); `sent`; `failed` = retriable while attempts < MAX_ATTEMPTS.
STATUS_PENDING = "pending"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUSES: tuple[str, ...] = (STATUS_PENDING, STATUS_SENT, STATUS_FAILED)

#: total send attempts per (receivable, rule, cycle) across runs; in-run transient retries do not count extra.
MAX_ATTEMPTS = 3
#: a `failed` log row is retried by later daily runs for this many days after its scheduled day.
RETRY_WINDOW_DAYS = 2
#: offsets are days relative to the due date: negative = before, 0 = on the day, positive = overdue.
MIN_OFFSET_DAYS, MAX_OFFSET_DAYS = -60, 365
DEFAULT_TIMEZONE = "America/Sao_Paulo"
DEFAULT_SEND_HOUR = 12

#: the template variables a rule may use (anything else is refused at save time).
TEMPLATE_VARIABLES: tuple[str, ...] = (
    "nome", "razao_social", "nome_fantasia", "valor", "vencimento", "link_pagamento", "pix_copia_cola", "dias_atraso",
)

# Skip reasons surfaced by the preview / run summary (stable codes).
SKIP_NO_CONTACT = "no_contact"
SKIP_NO_ADDRESS = "no_address_for_channel"
SKIP_OPT_OUT = "receivable_opt_out"
SKIP_BLOCKED = "blocked_by_host"
SKIP_NO_CHANNEL = "no_channel_configured"


@dataclass(frozen=True)
class ReminderContact:
    """Who/what a receivable's reminder is about -- supplied by the host (parties, a client table...)."""

    nome: str
    phone: Optional[str] = None
    email: Optional[str] = None
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    link_pagamento: Optional[str] = None
    pix_copia_cola: Optional[str] = None


@dataclass(frozen=True)
class PlannedReminder:
    """One message the engine would send (preview) or did attempt (run)."""

    entry_id: str
    rule_id: str
    channel: str
    offset_days: int
    cycle_date: str
    recipient: str
    text: str
    already: Optional[str] = None  # log status when the dedup ledger already has this key


@dataclass(frozen=True)
class SkippedReminder:
    entry_id: str
    rule_id: str
    reason: str


@dataclass
class ReminderPlan:
    org_id: str
    on: str
    planned: list[PlannedReminder] = field(default_factory=list)
    skipped: list[SkippedReminder] = field(default_factory=list)
