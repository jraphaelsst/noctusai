"""
Email utilities — templates + scheduled-digest sender + general-purpose
transactional sender (Protocol+Fake+Real+factory).

Sub-modules:
  - `templates` — `send_product_invitation_email` (existing; moved from
    `noctusai_lib.email_templates` 2026-04-25 by ai-expansion Tier 2 Phase 4).
  - `digest` — generic Resend/SMTP-backed digest helper for scheduled
    product digests (P3 pattern). Products bring their own `(html, text)`
    rendering; this module handles credential resolution + send +
    dry-run + structured return shape. Never raises.
  - `types` / `config` / `fake_adapter` / `smtp_adapter` / `factory` /
    `convenience` — the canonical Protocol+Fake+Real+factory sender
    (`EmailSender`), formalized 2026-09-23 (`cardhub-igig-crm` R7) at
    N=2 per `KB § PATTERNS/backend/seed-fake-real-adapter.md`. Unlike
    `send_digest`, `EmailSender.send(...)` RAISES on failure — a
    transactional send (an orçamento PDF, an invite, a "Testar envio"
    click) is a request the caller is actively waiting on, so a
    swallowed failure is a silent-error, not a resilience feature. Pick
    this family for anything with attachments, cc/bcc, reply-to, or
    threading headers (`In-Reply-To`/`References` — R8's reply watcher);
    pick `digest` for a fire-and-forget scheduled narrative.
"""
from .templates import send_product_invitation_email
from .digest import (
    Digest,
    DigestSendResult,
    send_digest,
    send_to_one,
    send_to_many,
)
from .types import Attachment, EmailSender, OutgoingEmail, SentEmail
from .config import SmtpConfig
from .errors import EmailError, EmailNotConfigured, EmailSendError
from .fake_adapter import FakeEmailSender
from .smtp_adapter import SmtpEmailSender
from .factory import make_email_sender
from .convenience import send_test

__all__ = [
    "send_product_invitation_email",
    "Digest",
    "DigestSendResult",
    "send_digest",
    "send_to_one",
    "send_to_many",
    "Attachment",
    "EmailSender",
    "OutgoingEmail",
    "SentEmail",
    "SmtpConfig",
    "EmailError",
    "EmailNotConfigured",
    "EmailSendError",
    "FakeEmailSender",
    "SmtpEmailSender",
    "make_email_sender",
    "send_test",
]
