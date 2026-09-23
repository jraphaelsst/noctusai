"""`SmtpEmailSender` — the Real adapter. Stdlib `smtplib` only; no
vendor SDK to lazy-import (SMTP is the vendor-neutral floor every
provider — Gmail, a self-hosted Postfix, igig's Integrações-page
credentials — answers to)."""
from __future__ import annotations

import asyncio
import logging
import re
import smtplib
import ssl as ssl_module
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Sequence

from .config import SmtpConfig
from .errors import EmailSendError
from .types import OutgoingEmail, SentEmail

logger = logging.getLogger(__name__)


@dataclass
class SmtpEmailSender:
    """SSL (465, implicit TLS) and STARTTLS (587) both supported via
    `SmtpConfig.security`; `"none"` sends unencrypted — only for local
    test servers that don't speak TLS at all.

    Generates a proper `Message-ID` from the sender's own domain when
    the caller doesn't supply one, and always returns it — R8's reply
    watcher threads a lead's reply back to this send by matching
    `In-Reply-To`/`References` against exactly this id, so a send that
    can't produce a stable id would leave R8 with nothing to match on
    (SMTP itself doesn't hand back a message id the way Resend's HTTP
    API does — the sender has to mint one).
    """

    config: SmtpConfig

    async def send(self, email: OutgoingEmail) -> SentEmail:
        if not email.to:
            raise EmailSendError(
                "OutgoingEmail.to must carry at least one recipient"
            )

        message = self._build_message(email)
        to_addrs = [*email.to, *email.cc, *email.bcc]

        # smtplib is sync; wrap in to_thread so the event loop stays
        # responsive while the TLS handshake + send round-trip complete.
        try:
            await asyncio.to_thread(self._send_sync, message, to_addrs)
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailSendError(
                f"SMTP auth failed for {self.config.username!r}: {exc}"
            ) from exc
        except smtplib.SMTPRecipientsRefused as exc:
            raise EmailSendError(
                f"recipients refused by {self.config.host}: {exc}"
            ) from exc
        except smtplib.SMTPException as exc:
            raise EmailSendError(f"SMTP send failed: {exc}") from exc
        except OSError as exc:
            raise EmailSendError(
                f"SMTP transport failed reaching "
                f"{self.config.host}:{self.config.port}: {exc}"
            ) from exc

        references_header = message.get("References")
        return SentEmail(
            message_id=str(message["Message-ID"]),
            in_reply_to=message.get("In-Reply-To"),
            references=tuple(references_header.split()) if references_header else (),
        )

    # ─── Internals ─────────────────────────────────────────────────────
    def _build_message(self, email: OutgoingEmail) -> EmailMessage:
        message = EmailMessage()
        message["From"] = _format_address(self.config.from_name, self.config.from_email)
        message["To"] = ", ".join(email.to)
        if email.cc:
            message["Cc"] = ", ".join(email.cc)
        # Bcc is deliberately NEVER set as a header — smtplib would
        # otherwise hand every listed recipient's copy the same header,
        # which defeats the point of a blind copy. Bcc recipients are
        # addressed only via the envelope (`to_addrs` in `_send_sync`).
        if email.reply_to:
            message["Reply-To"] = email.reply_to
        message["Subject"] = email.subject
        message["Message-ID"] = email.message_id or make_msgid(
            domain=_domain_of(self.config.from_email) or self.config.host
        )
        for key, value in email.headers.items():
            message[key] = value

        text_body = email.text or _strip_html(email.html or "")
        message.set_content(text_body)
        if email.html:
            message.add_alternative(email.html, subtype="html")

        for attachment in email.attachments:
            maintype, _, subtype = attachment.mime_type.partition("/")
            message.add_attachment(
                attachment.content,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=attachment.filename,
            )
        return message

    def _send_sync(self, message: EmailMessage, to_addrs: Sequence[str]) -> None:
        """Sync SMTP send. Runs inside `asyncio.to_thread`."""
        context = ssl_module.create_default_context()
        timeout = self.config.timeout_seconds

        if self.config.security == "ssl":
            with smtplib.SMTP_SSL(
                self.config.host, self.config.port, context=context, timeout=timeout,
            ) as smtp:
                smtp.login(self.config.username, self.config.password)
                smtp.send_message(
                    message, from_addr=self.config.from_email, to_addrs=list(to_addrs),
                )
            return

        with smtplib.SMTP(self.config.host, self.config.port, timeout=timeout) as smtp:
            if self.config.security == "starttls":
                smtp.starttls(context=context)
            smtp.login(self.config.username, self.config.password)
            smtp.send_message(
                message, from_addr=self.config.from_email, to_addrs=list(to_addrs),
            )


def _format_address(name: str, email_addr: str) -> str:
    return f"{name} <{email_addr}>" if name else email_addr


def _domain_of(email_addr: str) -> str:
    return email_addr.split("@", 1)[1] if "@" in email_addr else ""


def _strip_html(html: str) -> str:
    """Cheap HTML→text fallback — strips tags + collapses whitespace so
    the plaintext alternative is readable when the caller only supplies
    `html`. Same behaviour as social-wiring's product-local
    `email_service._strip_html`, which this module supersedes."""
    text = re.sub(r"<[^>]+>", "", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


__all__ = ["SmtpEmailSender"]
