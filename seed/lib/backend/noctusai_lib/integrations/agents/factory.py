"""Factory for the org-specs client: Real when the agents URL is configured, else refuse (never a silent Fake)."""
from __future__ import annotations

import logging
from typing import Optional

from noctusai_lib.integrations.agents.errors import AgentsNotConfigured
from noctusai_lib.integrations.agents.fake import FakeAgentsOrgSpecsClient
from noctusai_lib.integrations.agents.protocol import AgentsOrgSpecsClient
from noctusai_lib.integrations.agents.real import HttpAgentsOrgSpecsClient
from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse

logger = logging.getLogger(__name__)


def _refuse() -> AgentsOrgSpecsClient:
    raise AgentsNotConfigured("agents base URL is not configured", code="agents_not_configured")


def make_agents_org_specs_client(*, base_url: Optional[str], allow_fake: bool = False) -> AgentsOrgSpecsClient:
    """No base URL: the Fake only when `allow_fake` is explicitly set (dev/tests); otherwise raises
    `AgentsNotConfigured` (map it to a 503) -- prod is never answered by a scripted fake."""
    def _fake() -> AgentsOrgSpecsClient:
        logger.warning("agents base_url missing: using FakeAgentsOrgSpecsClient (dev only)")
        return FakeAgentsOrgSpecsClient()

    return resolve_fake_or_refuse(
        configured=bool(base_url),
        build_real=lambda: HttpAgentsOrgSpecsClient(base_url or ""),
        build_fake=_fake,
        allow_fake=allow_fake,
        unconfigured=_refuse,
    )
