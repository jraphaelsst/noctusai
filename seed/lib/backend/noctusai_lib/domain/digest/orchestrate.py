"""Build-and-send orchestration for digest pipelines.

Wraps `noctusai_lib.integrations.email.digest.send_digest(...)` and
normalizes the per-recipient return shape. Every product service ends
its `send_X(...)` with the same translation — `DigestSendResult` →
5-key dict. This helper owns that translation once.
"""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.integrations.email.digest import (
    Digest,
    DigestSendResult,
    send_digest,
)


async def build_and_send(
    digest: Digest,
    *,
    recipient: str,
    org_id: Optional[str],
    log_prefix: str,
) -> dict[str, Any]:
    """Send a built `Digest` and return the standardized 5-key result.

    Parameters:
        digest: A `Digest(subject, text, html)` built by the caller.
        recipient: Target email address.
        org_id: Threaded to `send_digest` for org-level credential
            resolution. May be None when sending to a platform-wide
            address.
        log_prefix: Short uppercase tag used in the underlying
            structured log (e.g. "AUDIT DIGEST", "PF MONTHLY").

    Returns:
        `{"sent": bool, "dry_run": bool, "external_id": Optional[str],
        "error": Optional[str], "subject": str}`. Never raises —
        upstream `send_digest` already swallows transport failures into
        `DigestSendResult.error`.
    """
    outcome: DigestSendResult = await send_digest(
        digest, recipient=recipient, org_id=org_id, log_prefix=log_prefix
    )
    return {
        "sent": outcome.sent,
        "dry_run": outcome.dry_run,
        "external_id": outcome.external_id,
        "error": outcome.error,
        "subject": digest.subject,
    }
