"""Deterministic in-memory org-specs client (dev/tests only -- the factory refuses it in prod)."""
from __future__ import annotations

from typing import Optional

from noctusai_lib.integrations.agents.errors import AgentsBadRequest, AgentsTokenInvalid
from noctusai_lib.integrations.agents.types import OrgSpecDeclarada, OrgSpecs


class FakeAgentsOrgSpecsClient:
    def __init__(self, declaradas: tuple[OrgSpecDeclarada, ...] = (), valores: Optional[dict[str, str]] = None,
                 *, agent_key: str = "fake"):
        self.agent_key = agent_key
        self.declaradas = declaradas
        self.valores = dict(valores or {})
        self.calls: list[tuple[str, str, Optional[dict[str, str]], str]] = []

    def _view(self, agent_key: str) -> OrgSpecs:
        faltando = tuple(d.chave for d in self.declaradas if d.obrigatoria and not self.valores.get(d.chave, "").strip())
        return OrgSpecs(agent_key=agent_key, declaradas=self.declaradas, valores=dict(self.valores), faltando=faltando)

    async def get_org_specs(self, agent_key: str, *, token: str) -> OrgSpecs:
        self.calls.append(("get", agent_key, None, token))
        if not token:
            raise AgentsTokenInvalid("no user token", code="unauthenticated")
        return self._view(agent_key)

    async def put_org_specs(self, agent_key: str, valores: dict[str, str], *, token: str) -> OrgSpecs:
        self.calls.append(("put", agent_key, dict(valores), token))
        if not token:
            raise AgentsTokenInvalid("no user token", code="unauthenticated")
        known = {d.chave for d in self.declaradas}
        unknown = sorted(set(valores) - known)
        if unknown:
            raise AgentsBadRequest("spec_nao_declarada", code="spec_nao_declarada")
        self.valores.update({k: v for k, v in valores.items() if v.strip()})
        for k, v in valores.items():
            if not v.strip():
                self.valores.pop(k, None)
        return self._view(agent_key)
