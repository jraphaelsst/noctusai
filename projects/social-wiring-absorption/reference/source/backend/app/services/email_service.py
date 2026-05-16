"""SMTP email sender — minimal wrapper for upload-completion notifications.

Single chokepoint for ``smtplib`` calls so the SMTP envelope shape stays
consistent + every send goes through the same retry / error funnel.
Phase 4 only needs ``send_email(to, subject, html_body)``; richer HTML
templating + bulk sends are deferred to the cross-product
``notification-templates-seed`` follow-up if a second product needs the
same shape.

Why product-local (not seed-side):
- N=1 — only YouTube Crawler ships SMTP today. Therapy uses Resend
  via its own service. Mailing uses its own SMTP-via-Mailgun shape.
- The ``CrawlerSettings.smtp_*`` fields are product-local config; lifting
  to seed would require a config-injection seam not yet justified.
- When a 2nd product needs SMTP, absorb into
  ``noctusai_lib.integrations.email`` with the canonical Protocol +
  Fake (logs-instead-of-sends) + Real (smtplib) + factory shape per
  ``KB § PATTERNS/seed-fake-real-adapter.md``.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

logger = logging.getLogger(__name__)


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
        render HTML; if None, we strip tags from ``html_body`` to
        produce a minimal fallback. Real templates ship both."""
        message = self._build_message(
            to=to,
            subject=subject,
            html_body=html_body,
            text_body=text_body or _strip_html(html_body),
        )

        # smtplib is sync; wrap in to_thread so the event loop stays
        # responsive while the SMTP handshake completes (TLS handshake
        # alone can be 100-300ms on first connection).
        try:
            await asyncio.to_thread(self._send_sync, message)
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailServiceError(
                f"SMTP auth failed for {self.smtp_user!r}: {exc}. "
                "Verify the App Password is current."
            ) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise EmailServiceError(
                f"Recipient {to!r} refused by SMTP server: {exc}. "
                "Bad address or upstream block."
            ) from exc
        except smtplib.SMTPException as exc:
            raise EmailServiceError(
                f"SMTP send failed for {to!r}: {exc}"
            ) from exc
        except OSError as exc:
            # Connection-level failure (DNS, TLS, network).
            raise EmailServiceError(
                f"SMTP transport failed reaching {self.smtp_host}:{self.smtp_port}: {exc}"
            ) from exc

    # ─── Internals ─────────────────────────────────────────────────────
    def _build_message(
        self, *, to: str, subject: str, html_body: str, text_body: str
    ) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self.smtp_user
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")
        return message

    def _send_sync(self, message: EmailMessage) -> None:
        """Sync SMTP send. Runs inside ``asyncio.to_thread``."""
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            host=self.smtp_host,
            port=self.smtp_port,
            context=context,
            timeout=30,
        ) as smtp:
            smtp.login(self.smtp_user, self.smtp_password)
            smtp.send_message(message)


def _strip_html(html: str) -> str:
    """Cheap HTML→text fallback. Not a full renderer — just strips tags
    + collapses whitespace so the plaintext alternative is readable."""
    import re
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
