"""SMTP email sender — thin shim over the seed's canonical
`noctusai_lib.integrations.email` sender.

Promoted 2026-09-23 (`cardhub-igig-crm` R7) — this module's own prior
docstring named the trigger exactly: "when a 2nd product needs SMTP,
absorb into `noctusai_lib.integrations.email` with the canonical
Protocol + Fake + Real + factory shape." igig's orçamento-PDF-to-lead
flow (R7) is that second product, and R8's reply watcher needs the same
`Message-ID` generation the new seed sender ships.

This module keeps its OWN public API (class name, constructor kwargs,
`send_email(...)` signature, exception types) unchanged — social-wiring
is live in prod and every call site (`notification_service.py`,
`settings_router.py`'s `/email/test`) depends on it — and delegates the
actual SMTP work to `noctusai_lib.integrations.email.SmtpEmailSender`.
Zero behaviour change: always SSL (this module never exposed a security
knob — `EmailService` always used `smtplib.SMTP_SSL`, so the shim pins
`security="ssl"` to match exactly)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from noctusai_lib.integrations.email import (
    EmailSendError as _SeedEmailSendError,
    OutgoingEmail,
    SmtpConfig,
    SmtpEmailSender,
)

_STRIP_TAGS_RE = re.compile(r"<[^>]+>")
_COLLAPSE_WHITESPACE_RE = re.compile(r"\s+")


class EmailServiceError(Exception):
    """All SMTP-side failures route through this — routers translate to
    HTTP. Distinct from generic Exception so the notification dispatcher
    can decide whether to retry (transient SMTP) vs. mark-failed (bad
    creds, malformed address)."""


class EmailNotConfigured(EmailServiceError):
    """SMTP_USER / SMTP_PASSWORD missing — refuse to dispatch. The
    Settings → API Keys tab surfaces this loudly so the operator can't
    silently end up with notifications going nowhere."""


@dataclass
class EmailService:
    """Constructed from settings; per-request is fine — connections are
    short-lived (one TCP open per send). For high-throughput cases a
    persistent SMTP connection would be the next step; not yet justified
    by upload volume (single uploads, low frequency)."""

    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str

    _sender: SmtpEmailSender = field(init=False, repr=False)

    def __post_init__(self):
        # Fail fast at construction so routers translate to a 503 with
        # an operator-actionable message, instead of a 500 trace at the
        # first send attempt.
        if not (self.smtp_user and self.smtp_password):
            raise EmailNotConfigured(
                "SMTP_USER / SMTP_PASSWORD missing. Configure Gmail App "
                "Password in .env (NOT the account password — see "
                "https://support.google.com/accounts/answer/185833)."
            )
        config = SmtpConfig(
            host=self.smtp_host,
            port=self.smtp_port,
            username=self.smtp_user,
            password=self.smtp_password,
            # Always implicit-TLS — this module never had a security
            # knob; it always called smtplib.SMTP_SSL directly. Pinning
            # "ssl" here is what makes the shim zero-behaviour-change.
            security="ssl",
            from_email=self.smtp_user,
        )
        self._sender = SmtpEmailSender(config)

    async def send_email(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
    ) -> None:
        """Send an HTML email. Raises :class:`EmailServiceError` on any
        SMTP failure; the caller (notification_service) translates to a
        per-recipient log row.

        ``text_body`` is the plaintext fallback for clients that don't
        render HTML; if None, the seed sender strips tags from
        ``html_body`` to produce a minimal fallback (same behaviour this
        module always had)."""
        email = OutgoingEmail(
            to=[to],
            subject=subject,
            html=html_body,
            text=text_body,
        )
        try:
            await self._sender.send(email)
        except _SeedEmailSendError as exc:
            raise EmailServiceError(str(exc)) from exc


def _strip_html(html: str) -> str:
    """Cheap HTML→text fallback. Not a full renderer — just strips tags
    + collapses whitespace so the plaintext alternative is readable.

    Kept here (duplicated from the seed's own private
    `smtp_adapter._strip_html`) because `tests/services/test_email_service.py`
    imports this symbol directly — it is this module's own public-ish
    surface, not exercised by `send_email` anymore (the seed sender does
    its own stripping internally when `text` is omitted)."""
    text = _STRIP_TAGS_RE.sub("", html)
    text = _COLLAPSE_WHITESPACE_RE.sub(" ", text)
    return text.strip()
