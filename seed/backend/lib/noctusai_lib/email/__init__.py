"""
Email utilities — templates + scheduled-digest sender.

Sub-modules:
  - `templates` — `send_product_invitation_email` (existing; moved from
    `noctusai_lib.email_templates` 2026-04-25 by ai-expansion Tier 2 Phase 4).
  - `digest` — generic Resend-backed digest helper for scheduled product
    digests (P3 pattern). Products bring their own `(html, text)` rendering;
    this module handles credential resolution + send + dry-run + structured
    return shape.
"""
from noctusai_lib.email.templates import send_product_invitation_email
from noctusai_lib.email.digest import (
    Digest,
    DigestSendResult,
    send_digest,
)

__all__ = [
    "send_product_invitation_email",
    "Digest",
    "DigestSendResult",
    "send_digest",
]
