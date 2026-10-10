"""Resend platform APIs beyond sending (sending lives in `integrations.email`)."""
from .domains import (
    DomainRecord,
    FakeResendDomains,
    HttpResendDomains,
    ResendDomainsError,
    ResendDomains,
    ResendNotConfigured,
    make_resend_domains,
)

__all__ = [
    "DomainRecord", "FakeResendDomains", "HttpResendDomains", "ResendDomainsError",
    "ResendDomains", "ResendNotConfigured", "make_resend_domains",
]
