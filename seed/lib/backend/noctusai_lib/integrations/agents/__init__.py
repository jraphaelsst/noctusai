"""agents-product client seam: shared errors + HTTP transport + the org-specs (org context) surface.

`make_agents_org_specs_client(base_url=..., allow_fake=...)` -> `AgentsOrgSpecsClient` (Protocol; Fake + Http).
Product channel clients (social-wiring) extend `AgentsHttpTransport` and subclass `AgentsClientError`.
KB § INTEGRATIONS/agents-org-specs.md.
"""
from __future__ import annotations

from noctusai_lib.integrations.agents.errors import (
    AgentNotFound,
    AgentsBadRequest,
    AgentsClientError,
    AgentsNotConfigured,
    AgentsTimeout,
    AgentsTokenInvalid,
    AgentsUpstreamError,
)
from noctusai_lib.integrations.agents.factory import make_agents_org_specs_client
from noctusai_lib.integrations.agents.fake import FakeAgentsOrgSpecsClient
from noctusai_lib.integrations.agents.protocol import AgentsOrgSpecsClient
from noctusai_lib.integrations.agents.real import (
    DEFAULT_RETRY_AFTER_S,
    DEFAULT_TIMEOUT_S,
    AgentsHttpTransport,
    HttpAgentsOrgSpecsClient,
    error_code,
    need,
    opt_str,
    parse_org_specs,
    raise_for_agents_status,
    retry_after,
)
from noctusai_lib.integrations.agents.types import OrgSpecDeclarada, OrgSpecs

__all__ = [
    "AgentNotFound", "AgentsBadRequest", "AgentsClientError", "AgentsHttpTransport", "AgentsNotConfigured",
    "AgentsOrgSpecsClient", "AgentsTimeout", "AgentsTokenInvalid", "AgentsUpstreamError", "DEFAULT_RETRY_AFTER_S",
    "DEFAULT_TIMEOUT_S", "FakeAgentsOrgSpecsClient", "HttpAgentsOrgSpecsClient", "OrgSpecDeclarada", "OrgSpecs",
    "error_code", "make_agents_org_specs_client", "need", "opt_str", "parse_org_specs", "raise_for_agents_status",
    "retry_after",
]
