"""The single seam consumers reach for — Fake or Real, by flag."""

from __future__ import annotations

from typing import Any, Optional, Union

from .endpoints import OLX_LEAD_MANAGER_BASE_URL
from .fake import FakeOlxLeadManagerClient
from .real import DEFAULT_TIMEOUT_SECONDS, OlxLeadManagerClient


def make_olx_lead_manager_client(
    *,
    use_fake: bool = False,
    api_key: Optional[str] = None,
    agent_name: Optional[str] = None,
    base_url: str = OLX_LEAD_MANAGER_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    http_client: Any = None,
    fake_configured: bool = True,
    fake_response: Optional[dict[str, Any]] = None,
) -> Union[OlxLeadManagerClient, FakeOlxLeadManagerClient]:
    """Build an OLX Gestor de Leads client.

    Both branches expose the same surface (`push_lead`,
    `connection_status`, `configured`), so a consumer selects here and
    never branches on environment itself.

    `use_fake=False` with no credentials does NOT raise — it returns a
    real client that raises `OlxConfigError` on first call. That is the
    seed's leniency contract: an unconfigured tenant must not stop the
    host app from starting.
    """
    if use_fake:
        return FakeOlxLeadManagerClient(
            configured=fake_configured, response=fake_response
        )
    return OlxLeadManagerClient(
        api_key,
        agent_name,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        http_client=http_client,
    )


__all__ = ["make_olx_lead_manager_client"]
