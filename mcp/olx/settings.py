"""OLX connector settings — per-CRM credentials + our own receiver.

Four values, two independent capabilities, and it matters that they are
independent: the OUTBOUND Gestor de Leads surface (`OLX_API_KEY` +
`OLX_AGENT_NAME`) and the INBOUND receiver simulation (`OLX_RECEIVER_URL`
+ `OLX_WEBHOOK_SECRET`) are configured separately and usually at
different times. A single `configured` flag would report the whole
connector dead because one half is not set up yet.

Secrets live in this connector's own gitignored `mcp/olx/.env` — every
connector owns its auth store rather than inheriting the repo `.env`
(`KB § CONTEXT/INTEGRATIONS/vista.md § 1`).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings
from noctusai_lib.integrations.olx import OLX_LEAD_MANAGER_BASE_URL


@dataclass(frozen=True)
class OlxConnectorSettings(ConnectorSettings):
    """Frozen per-CRM config (a tool handler cannot corrupt server state).

    - `api_key` / `agent_name` — Gestor de Leads credentials, sent as
      `X-API-KEY` / `X-Agent-Name`. Secret.
    - `webhook_secret` — the per-CRM key OLX sends back as the second
      half of `Basic base64("vivareal:<secret>")`. Secret. One per CRM,
      NOT per advertiser.
    - `receiver_url` — OUR endpoint, the one registered with OLX at
      homologation. `olx.webhook.simulate` posts here.
    - `base_url` / `timeout_seconds` — pure defaults, off `env_map`.
    """

    api_key: Optional[str] = None
    agent_name: Optional[str] = None
    webhook_secret: Optional[str] = None
    receiver_url: Optional[str] = None
    base_url: str = OLX_LEAD_MANAGER_BASE_URL
    timeout_seconds: float = 20.0

    @property
    def lead_manager_configured(self) -> bool:
        """Outbound `POST /v1/addLeads` is usable. Credential VALIDITY is
        a separate live question — `olx.leads.push` is the only thing
        that can answer it, which is why Gate 1 uses it."""
        return bool(self.api_key) and bool(self.agent_name)

    @property
    def receiver_configured(self) -> bool:
        """`olx.webhook.simulate` can exercise our own receiver."""
        return bool(self.receiver_url) and bool(self.webhook_secret)

    @property
    def configured(self) -> bool:
        """The kit's generic flag. True when EITHER capability is usable —
        the connector is useful with just one half set up (the zero-IO
        contract tools need neither)."""
        return self.lead_manager_configured or self.receiver_configured


get_settings = make_get_settings(
    OlxConnectorSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "api_key": "OLX_API_KEY",
        "agent_name": "OLX_AGENT_NAME",
        "webhook_secret": "OLX_WEBHOOK_SECRET",
        "receiver_url": "OLX_RECEIVER_URL",
    },
)


__all__ = ["OlxConnectorSettings", "get_settings"]
