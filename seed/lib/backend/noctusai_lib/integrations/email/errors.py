"""Typed errors for the general-purpose email-sending seam.

Distinct from `digest.py`'s swallow-and-return-a-result contract
(`DigestSendResult` never raises — a scheduled digest must not crash the
calling endpoint). `EmailSender.send(...)` is the opposite shape on
purpose: a transactional send (orçamento PDF to a lead, an invite, a
"Testar envio" button) is a request the caller is actively waiting on,
so a swallowed failure there is a silent-error — the caller must see it.
"""
from __future__ import annotations


class EmailError(Exception):
    """Base for every seed email-sending failure."""


class EmailNotConfigured(EmailError):
    """SMTP host/port/username/password don't all resolve — refuse to
    build a Real sender rather than construct one that will fail on
    first send. Mirrors `digest._resolve_smtp_config`'s completeness
    check so both paths agree on what "configured" means."""


class EmailSendError(EmailError):
    """SMTP transport / auth / recipient failure at send time. Carries
    the underlying `smtplib`/`OSError` message; callers translate to an
    HTTP response or a per-recipient log row as needed."""


__all__ = ["EmailError", "EmailNotConfigured", "EmailSendError"]
