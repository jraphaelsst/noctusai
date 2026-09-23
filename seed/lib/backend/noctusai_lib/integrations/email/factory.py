"""The single seam consumers reach for — Fake or Real, by presence of a
config."""
from __future__ import annotations

from typing import Optional, Union

from .config import SmtpConfig
from .fake_adapter import FakeEmailSender
from .smtp_adapter import SmtpEmailSender


def make_email_sender(
    config: Optional[SmtpConfig] = None,
) -> Union[SmtpEmailSender, FakeEmailSender]:
    """Build an `EmailSender`.

    `config=None` (no SMTP credentials resolved for this org/platform)
    returns a `FakeEmailSender` — the expected "not configured yet"
    state, mirroring `make_olx_lead_manager_client`'s leniency contract:
    a tenant that hasn't set up email yet must not stop the host app
    from starting or the caller from exercising the send path in tests.
    A `config` present returns the Real SMTP sender.
    """
    if config is None:
        return FakeEmailSender()
    return SmtpEmailSender(config)


__all__ = ["make_email_sender"]
