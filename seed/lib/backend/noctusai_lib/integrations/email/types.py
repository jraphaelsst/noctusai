"""Value objects + the `EmailSender` Protocol.

Formalized 2026-09-23 (`cardhub-igig-crm` R7) at N=2 — social-wiring's
product-local `email_service.py` said explicitly to promote "when a 2nd
product needs SMTP"; igig's orçamento-PDF-to-lead flow (R7) is that
second consumer, with a third need already named (R8's reply watcher,
which threads by `In-Reply-To`/`References` against the `Message-ID`
this sender returns).

Deliberately NOT `digest.Digest`/`DigestSendResult` — those model a
scheduled narrative send that never raises and has no attachments, cc,
or threading headers. `OutgoingEmail` models a general transactional
send: attachments (the PDF), reply-to, and caller-set headers for
threading. Two different shapes for two different jobs; forcing one
into the other would make one of them lie about what it does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


@dataclass(frozen=True)
class Attachment:
    """One file attached to an `OutgoingEmail`. `content` is raw bytes —
    the caller has already rendered the PDF/image/etc.; this module
    never generates attachment content itself."""

    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"


@dataclass
class OutgoingEmail:
    """Everything one send needs. `headers` is the escape hatch for
    threading (`In-Reply-To`, `References`) and anything else a caller
    needs verbatim on the wire — `EmailSender` implementations must not
    special-case any header name beyond what they set themselves
    (`Message-ID`) or clobber."""

    to: list[str]
    subject: str
    html: Optional[str] = None
    text: Optional[str] = None
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    reply_to: Optional[str] = None
    attachments: list[Attachment] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    message_id: Optional[str] = None
    """Caller-supplied `Message-ID` (e.g. for an idempotent resend).
    `None` (the common case) lets the Real sender generate one from the
    sender's own domain, and the Fake generate a deterministic stub —
    neither ever sends without one, since R8's reply watcher threads on
    it."""


@dataclass(frozen=True)
class SentEmail:
    """Outcome of a successful send. Unlike `digest.DigestSendResult`,
    `EmailSender.send(...)` raises on failure rather than returning a
    result object — see `errors.py` for why."""

    message_id: str
    in_reply_to: Optional[str] = None
    references: tuple[str, ...] = ()
    """Echoes `OutgoingEmail.headers["References"]` (split on
    whitespace, RFC 5322 shape) so a caller persisting the sent row
    doesn't have to re-parse its own headers dict."""


@runtime_checkable
class EmailSender(Protocol):
    """Surface every email sender implements. `FakeEmailSender` and
    `SmtpEmailSender` both satisfy this Protocol naturally — consumers
    depend on it, never on `smtplib` or a specific transport."""

    async def send(self, email: OutgoingEmail) -> SentEmail: ...


__all__ = ["Attachment", "EmailSender", "OutgoingEmail", "SentEmail"]
