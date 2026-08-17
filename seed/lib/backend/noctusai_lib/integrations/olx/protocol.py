"""Adapter contract for the OUTBOUND direction — pushing leads to OLX.

Direction matters here and is easy to get backwards. The lead feed we
actually want is INBOUND (OLX POSTs to us) and needs no adapter — it is
`webhook.parse_olx_lead_webhook` plus a receiver.

This Protocol covers the other direction: `POST /v1/addLeads` on the
Gestor de Leads receiver, which pushes a lead we hold INTO OLX's lead
manager. Two reasons it ships now rather than later:

1. It is the only authenticated endpoint OLX exposes to us, so it is the
   only way to prove a key works before homologation traffic starts —
   Gate 1 leans on it.
2. Sending leads to OLX is a real product need the moment we originate
   leads elsewhere and want them in the client's OLX inbox.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol


class OlxLeadManagerAdapter(Protocol):
    """Outbound Gestor de Leads surface — async."""

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
        """`POST /v1/addLeads`. Returns the decoded response body.

        `business_type` is `SALE` or `RENTAL` — note that these are NOT
        the `SELL`/`RENT` the inbound webhook uses. The vendor is
        inconsistent across its own two surfaces; anything mapping
        between the two directions must translate rather than pass
        through.

        Raises the adapter's typed error on any non-2xx. Never returns a
        partial success.
        """
        ...

    async def connection_status(self) -> dict[str, Any]:
        """Configuration state WITHOUT calling the API.

        `{ok, configured, base_url, has_api_key, has_agent_name, next_step}`.
        Zero requests on purpose — an agent asking "is this set up?"
        should not spend a call, and an unconfigured connector should not
        produce an upstream error that reads like an outage.
        """
        ...


__all__ = ["OlxLeadManagerAdapter"]
