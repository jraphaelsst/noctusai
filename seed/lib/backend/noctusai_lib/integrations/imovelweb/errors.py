"""Error hierarchy + secret redaction for the ImovelWeb connector.

Three levels, and the split between the middle two is the point:
`ImovelWebConfigError` means *we* are not set up, `ImovelWebUpstreamError`
means the vendor failed. Collapsing them makes an unconfigured tenant look
like an outage, and an operator who has seen that once stops trusting the
status page.
"""

from __future__ import annotations

from typing import Optional

#: Redaction placeholder. Distinctive enough to grep for in a log dump.
SECRET_REDACTION_PLACEHOLDER = "***REDACTED***"

#: Below this length a "secret" is more likely a common substring than a
#: credential, and redacting it would mangle unrelated text. Mirrors the
#: guard in `vista/client.py::redact_api_key` and `olx/errors.py`.
_MIN_REDACTABLE_LENGTH = 4


def redact_secrets(text: Optional[str], *secrets: Optional[str]) -> Optional[str]:
    """Strip every supplied secret out of `text`.

    Call this at EVERY boundary that can surface a string to a human or a
    model — exception messages, log lines, MCP tool results. An MCP result
    goes straight into a model's context window, so a leaked credential
    there is a credential in a transcript.

    This connector holds **three** secrets, not one: the OAuth
    `client_secret`, the bearer token it exchanges for, and the callback
    authorization header value we register with the vendor. All three must
    be passed.

    NOC-REMEDIATE[dry-lift]: this is the third instance of the same helper
    (`vista/client.py::redact_api_key`, `olx/errors.py::redact_secret`,
    here), so the recurrence rule says it MUST formalize to
    `noctusai_lib/integrations/redaction.py::redact_secrets`. The lift is
    sequenced rather than waived: it rewrites `vista/client.py` and
    `olx/endpoints.py`, which belong to a branch still in flight. Do it
    once that branch lands, keeping the two existing names as thin aliases.
    """
    if text is None:
        return None
    result = text
    for secret in secrets:
        if secret and len(secret) >= _MIN_REDACTABLE_LENGTH:
            result = result.replace(secret, SECRET_REDACTION_PLACEHOLDER)
    return result


class ImovelWebError(Exception):
    """Base for every ImovelWeb connector failure.

    Catch subclasses BEFORE this one — `ImovelWebConfigError` and
    `ImovelWebUpstreamError` both inherit from it, so an `except
    ImovelWebError` placed first swallows the distinction the hierarchy
    exists to preserve.
    """

    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class ImovelWebConfigError(ImovelWebError):
    """We are not configured to talk to ImovelWeb.

    Maps to HTTP **424 Failed Dependency**, not 500 and not 502. This is
    gated-capability honesty: "no credentials have been entered for this
    tenant" is a different fact from "the vendor is down", and the caller
    can act on the first without paging anyone.

    Raised on the first *call*, never at construction — an unconfigured
    tenant must not stop the host app from starting.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status=424)


class ImovelWebUpstreamError(ImovelWebError):
    """ImovelWeb returned an error, or was unreachable.

    Carries the vendor's own status when there was one, so a 429 stays a
    429 and a caller can back off intelligently; falls back to 502 when the
    failure was at the transport layer and there is no vendor status to
    report.
    """

    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        super().__init__(message, status=status or 502)


__all__ = [
    "SECRET_REDACTION_PLACEHOLDER",
    "ImovelWebConfigError",
    "ImovelWebError",
    "ImovelWebUpstreamError",
    "redact_secrets",
]
