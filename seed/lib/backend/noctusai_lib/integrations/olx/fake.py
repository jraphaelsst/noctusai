"""Deterministic in-memory `OlxLeadManagerAdapter` — the dev/test default.

Records instead of sending. `pushed` is the assertion surface: a test
checks what would have gone to OLX without a network, a key, or a
homologated integration.
"""

from __future__ import annotations

from typing import Any, Optional

from .errors import OlxConfigError, OlxUpstreamError


class FakeOlxLeadManagerClient:
    """In-memory stand-in for `OlxLeadManagerClient`.

    `configured=False` exercises the unconfigured-tenant branch (raises
    `OlxConfigError`, same as the real client). `fail_with` injects an
    upstream failure so a caller's retry/error path is testable without
    a live 500.
    """

    def __init__(
        self,
        *,
        configured: bool = True,
        response: Optional[dict[str, Any]] = None,
        fail_with: Optional[Exception] = None,
    ) -> None:
        self._configured = configured
        self._response = response if response is not None else {"status": "OK"}
        self._fail_with = fail_with
        #: Every accepted push, in order. The assertion surface.
        self.pushed: list[dict[str, Any]] = []

    @property
    def configured(self) -> bool:
        return self._configured

    async def connection_status(self) -> dict[str, Any]:
        return {
            "ok": self._configured,
            "configured": self._configured,
            "base_url": "https://fake.olx.local",
            "has_api_key": self._configured,
            "has_agent_name": self._configured,
            "next_step": None if self._configured else "Fake is unconfigured by request.",
            "fake": True,
        }

    async def push_lead(
        self,
        *,
        lead_name: str,
        lead_email: Optional[str] = None,
        lead_telephone: Optional[str] = None,
        message: Optional[str] = None,
        external_id: Optional[str] = None,
        business_type: Optional[str] = None,
        broker_email: Optional[str] = None,
        lead_origin: Optional[str] = None,
    ) -> dict[str, Any]:
        if not self._configured:
            raise OlxConfigError("OLX Gestor de Leads is not configured (fake).")
        if self._fail_with is not None:
            raise self._fail_with
        # The real client rejects the inbound vocabulary loudly; the Fake
        # must too, or a test passes against a call production refuses.
        if business_type is not None and business_type not in ("SALE", "RENTAL"):
            raise ValueError(
                f"business_type must be 'SALE' or 'RENTAL' (got {business_type!r})."
            )
        record = {
            "LeadName": lead_name,
            "LeadEmail": lead_email,
            "LeadTelephone": lead_telephone,
            "Message": message,
            "ExternalId": external_id,
            "BusinessType": business_type,
            "BrokerEmail": broker_email,
            "LeadOrigin": lead_origin,
        }
        self.pushed.append(record)
        return dict(self._response)


def upstream_failure(status: int = 500, message: str = "fake upstream failure") -> OlxUpstreamError:
    """Convenience for `fail_with=` in tests."""
    return OlxUpstreamError(message, status=status)


__all__ = ["FakeOlxLeadManagerClient", "upstream_failure"]
