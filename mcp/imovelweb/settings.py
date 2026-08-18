"""ImovelWeb connector settings — vendor credentials + our own receiver.

Six values, **two independent capabilities**, and the independence is the
point:

- the OUTBOUND OpenNavent API (`IMOVELWEB_CLIENT_ID` +
  `IMOVELWEB_CLIENT_SECRET`), issued by `integracao@imovelweb.com.br`;
- the INBOUND receiver simulation (`IMOVELWEB_RECEIVER_URL` +
  `IMOVELWEB_WEBHOOK_SECRET`), whose secret **we choose** — the vendor
  never issues it, which is the one way this integration is easier than
  Grupo OLX's.

They are configured at different times, so a single `configured` flag
would report the whole connector dead because one half is not set up yet.

Secrets live in this connector's own gitignored `mcp/imovelweb/.env` —
every connector owns its auth store rather than inheriting the repo `.env`
(`KB § CONTEXT/INTEGRATIONS/vista.md § 1`).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings
from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_SANDBOX_WINDOW,
    base_url as resolve_base_url,
)

#: Values `IMOVELWEB_SANDBOX` accepts as true. Anything else — including a
#: typo — is false, because defaulting to sandbox=False means the guard in
#: `emit_event` refuses rather than fires synthetic leads somewhere real.
_TRUTHY = frozenset({"1", "true", "yes", "on", "sandbox"})


@dataclass(frozen=True)
class ImovelWebConnectorSettings(ConnectorSettings):
    """Frozen config (a tool handler cannot corrupt server state).

    `region_setting` / `sandbox_setting` carry the RAW env strings rather
    than parsed values because `make_get_settings` passes `None` for every
    unset variable — a field declared as `region: str = "br"` would be
    clobbered to `None` the moment the var is absent, which is exactly
    when the default is supposed to apply. The derived properties below
    are what callers read.
    """

    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    webhook_secret: Optional[str] = None
    receiver_url: Optional[str] = None
    region_setting: Optional[str] = None
    sandbox_setting: Optional[str] = None
    base_url_setting: Optional[str] = None
    timeout_seconds: float = 20.0

    # -- derived ----------------------------------------------------------

    @property
    def region(self) -> str:
        return (self.region_setting or "br").strip().lower()

    @property
    def sandbox(self) -> bool:
        return (self.sandbox_setting or "").strip().lower() in _TRUTHY

    @property
    def sandbox_window(self) -> Optional[str]:
        """The vendor's sandbox is up roughly 07:00-21:00 UTC-3. Surfaced
        so a timeout outside that window reads as "closed", not "broken"."""
        return IMOVELWEB_SANDBOX_WINDOW if self.sandbox else None

    @property
    def base_url(self) -> Optional[str]:
        """The host every credentialed call goes to.

        `None` for an unknown region rather than a silent fall back to
        production — a sandbox call that quietly hit prod would fire
        synthetic leads into a live CRM.
        """
        if self.base_url_setting:
            return self.base_url_setting.rstrip("/")
        try:
            return resolve_base_url(self.region, sandbox=self.sandbox)
        except ValueError:
            return None

    # -- capability gates --------------------------------------------------

    @property
    def api_configured(self) -> bool:
        """The OpenNavent surface is usable. Credential VALIDITY is a
        separate live question that only `imovelweb.diagnostics.probe` or
        a real call can answer."""
        return bool(self.client_id) and bool(self.client_secret) and bool(self.base_url)

    @property
    def receiver_configured(self) -> bool:
        """`imovelweb.webhook.simulate` can exercise our own receiver."""
        return bool(self.receiver_url) and bool(self.webhook_secret)

    @property
    def configured(self) -> bool:
        """The kit's generic flag. True when EITHER capability is usable —
        the connector is useful with just one half, and the contract tools
        need neither."""
        return self.api_configured or self.receiver_configured

    @property
    def known_secrets(self) -> tuple[Optional[str], ...]:
        """Everything that must never appear in a tool result. An MCP
        result goes straight into a model's context window, so a leaked
        credential there is a credential in a transcript."""
        return (self.client_secret, self.webhook_secret)


get_settings = make_get_settings(
    ImovelWebConnectorSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "client_id": "IMOVELWEB_CLIENT_ID",
        "client_secret": "IMOVELWEB_CLIENT_SECRET",
        "webhook_secret": "IMOVELWEB_WEBHOOK_SECRET",
        "receiver_url": "IMOVELWEB_RECEIVER_URL",
        "region_setting": "IMOVELWEB_REGION",
        "sandbox_setting": "IMOVELWEB_SANDBOX",
        "base_url_setting": "IMOVELWEB_BASE_URL",
    },
)


__all__ = ["ImovelWebConnectorSettings", "get_settings"]
