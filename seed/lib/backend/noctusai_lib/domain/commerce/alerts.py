"""Staff alerts -- the store's `contact_email` hears about money events that need a human.

Used for: a chargeback opened / lost, a payment that landed on a superseded charge attempt,
a payment for a cancelled / closed order, a refused invoice cancel. An alert NEVER raises
(it must not undo the money state it reports): a missing recipient or mailer, or a send
failure, is logged at the right level and reported through the return value -- never silent.
PII: the body carries the order's short id and amounts, never the buyer's name / document.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.integrations.email.types import EmailSender, OutgoingEmail

from .profile import get_profile

logger = logging.getLogger(__name__)


async def notify_staff(
    db: Any,
    org_id: Any,
    email: Optional[EmailSender],
    *,
    subject: str,
    lines: list[str],
) -> bool:
    """Mail the store's contact address. Returns True only when a message was handed to the sender."""
    profile = get_profile(db, org_id) or {}
    to = (profile.get("contact_email") or "").strip()
    store = profile.get("trade_name") or "Loja"
    if not to:
        logger.warning("commerce alert NOT sent (org=%s has no contact_email): %s", org_id, subject)
        return False
    if email is None:
        logger.warning("commerce alert NOT sent (no e-mail sender configured; org=%s): %s", org_id, subject)
        return False
    text = "\n".join([*lines, "", f"-- {store}"])
    html = "".join(f"<p>{line}</p>" for line in lines) + f"<p>-- {store}</p>"
    try:
        await email.send(OutgoingEmail(to=[to], subject=subject, html=html, text=text))
    except Exception:  # noqa: BLE001 - an alert must never undo the state it reports
        logger.error("commerce alert e-mail failed (org=%s): %s", org_id, subject, exc_info=True)
        return False
    return True


__all__ = ["notify_staff"]
