"""Connector-local error taxonomy + gates for the OLX MCP.

Deliberately thin. There is no connector-side HTTP here for the vendor
API: `noctusai_lib.integrations.olx` owns that client, and this module
only maps its errors into the connector's own type so every tool's
`error` envelope has one shape regardless of which layer raised.
"""
from __future__ import annotations

from typing import Optional

from _kit.errors import confirmation_required_message
from noctusai_lib.integrations.olx import OlxConfigError, OlxError


class OlxApiError(Exception):
    """Connector-side error carrying an HTTP-ish `status`.

    424 = not configured · 412 = confirmation required · 502 = upstream
    unreachable/undecodable · anything else = the vendor's own status,
    passed through.
    """

    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class ConfirmationRequiredError(OlxApiError):
    """A write tool was called without `confirm=true`.

    Raised BEFORE any side effect — the gate is the point, so it must be
    the first thing the handler evaluates.
    """

    def __init__(self, action: str, effect: str = "") -> None:
        super().__init__(
            confirmation_required_message(action, effect, noun="write action"),
            status=412,
        )


def require_lead_manager_configured(settings) -> None:
    """Gate the outbound Gestor de Leads surface."""
    if not settings.lead_manager_configured:
        raise OlxApiError(
            "OLX Gestor de Leads is not configured — set OLX_API_KEY and "
            "OLX_AGENT_NAME in mcp/olx/.env. Both are issued during the "
            "Gestor de Leads setup (integracaoleads@grupozap.com).",
            status=424,
        )


def require_receiver_configured(settings) -> None:
    """Gate `olx.webhook.simulate`, which POSTs at OUR receiver."""
    if not settings.receiver_configured:
        raise OlxApiError(
            "The OLX receiver is not configured — set OLX_RECEIVER_URL and "
            "OLX_WEBHOOK_SECRET in mcp/olx/.env. The secret is the per-CRM "
            "key OLX issues at homologation; it must match what the product "
            "receiver validates, or the simulation proves nothing.",
            status=424,
        )


def map_seed_error(exc: BaseException) -> OlxApiError:
    """Seed error → connector error, preserving status and message.

    Subclass before parent: `OlxConfigError` is an `OlxError`, and
    collapsing them would erase the difference between "we are not set
    up" (fixable by configuration) and "OLX said no" (theirs, maybe
    transient).
    """
    if isinstance(exc, OlxApiError):
        return exc
    if isinstance(exc, OlxConfigError):
        return OlxApiError(exc.message, status=424)
    if isinstance(exc, OlxError):
        return OlxApiError(exc.message, status=exc.status or 502)
    return OlxApiError(str(exc), status=502)


__all__ = [
    "ConfirmationRequiredError",
    "OlxApiError",
    "map_seed_error",
    "require_lead_manager_configured",
    "require_receiver_configured",
]
