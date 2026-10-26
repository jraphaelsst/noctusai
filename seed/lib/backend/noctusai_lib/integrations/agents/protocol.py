"""Protocol of the org-specs surface of agents.

`token` is the LOGGED-IN USER's bearer, forwarded as-is: agents' `require_admin` and RLS decide who
may read/write the org's context. A service credential here would let a non-admin edit it.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from noctusai_lib.integrations.agents.types import OrgSpecs


@runtime_checkable
class AgentsOrgSpecsClient(Protocol):
    async def get_org_specs(self, agent_key: str, *, token: str) -> OrgSpecs: ...

    async def put_org_specs(self, agent_key: str, valores: dict[str, str], *, token: str) -> OrgSpecs: ...
