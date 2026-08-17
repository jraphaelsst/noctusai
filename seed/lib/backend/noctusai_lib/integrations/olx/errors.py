"""Typed errors for the OLX integration.

Subclass-before-parent catch order matters: `OlxConfigError` and
`OlxUpstreamError` are both `OlxError`, so a handler that catches the
parent first swallows the distinction between "we are not set up" (424,
our fault, fixable by configuration) and "OLX said no" (their status,
possibly transient).
"""

from __future__ import annotations

from typing import Optional


class OlxError(Exception):
    """Base for every OLX integration failure."""

    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class OlxConfigError(OlxError):
    """Credentials or base URL absent. HTTP 424 — gated-capability
    honesty: the capability exists but is not configured, which is not
    the same as an outage and must not be reported as one."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status=424)


class OlxUpstreamError(OlxError):
    """OLX answered non-2xx, or was unreachable / returned non-JSON.

    `status` carries OLX's own status when there was one, else 502.
    """


def redact_secret(text: str, *secrets: Optional[str]) -> str:
    """Strip any of `secrets` out of `text` before it reaches a log, an
    error message or an agent's context.

    Vendors echo credentials in error bodies (vista does it on 401), and
    an MCP tool result goes straight into a model's context window where
    it may be persisted or summarised. Redact at the boundary, always —
    it costs nothing when there is nothing to redact.
    """
    out = text
    for secret in secrets:
        if secret and len(secret) >= 4:
            out = out.replace(secret, "***redacted***")
    return out


__all__ = [
    "OlxConfigError",
    "OlxError",
    "OlxUpstreamError",
    "redact_secret",
]
