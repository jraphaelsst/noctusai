"""`send_test` — the "Testar envio" button's zero-effort default.

A Settings/Integrações page's test button just wants "prove these SMTP
creds work" without hand-rolling an `OutgoingEmail`. Products with
richer copy (social-wiring's own `/email/test` endpoint composes its
own Portuguese subject/body) should keep doing that — this is the
default for a product that hasn't written one yet.
"""
from __future__ import annotations

from .types import EmailSender, OutgoingEmail, SentEmail

_DEFAULT_SUBJECT = "Teste de envio"


async def send_test(
    sender: EmailSender,
    *,
    to: str,
    subject: str = _DEFAULT_SUBJECT,
    from_label: str = "NoctusAI",
) -> SentEmail:
    """Send a minimal round-trip test email through any `EmailSender`
    (`FakeEmailSender` or `SmtpEmailSender` — the caller already decided
    which via `make_email_sender`)."""
    text = (
        f"Teste de envio SMTP via {from_label}. "
        "Se você recebeu esta mensagem, o envio está funcional."
    )
    html = (
        f"<p>Teste de envio SMTP via <strong>{from_label}</strong>.</p>"
        "<p>Se você recebeu esta mensagem, o envio está funcional.</p>"
    )
    email = OutgoingEmail(to=[to], subject=subject, text=text, html=html)
    return await sender.send(email)


__all__ = ["send_test"]
