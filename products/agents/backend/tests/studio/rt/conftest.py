"""Fixtures for the BE-RT suite (Agent Studio runtime, conversations, eval
runner, importer, app wiring).

``rt`` drives the REAL product app (``app.main.app``) — the one BE-RT wires —
through the shared ``agents_client`` fixture (Julia's stores/runtime/broker
already bound to shared Fakes), and additionally binds every studio store
seam onto shared Fakes via ``app.dependency_overrides``. The production seam
bindings ``install_studio_seams`` put on the app (eval gate, knowledge
catalog, eval scheduler) are SAVED and RESTORED around each test, never
popped — later tests keep seeing the production wiring.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest

from app.routers.studio_agents_router import get_studio_definition_store_dep
from app.routers.studio_evals_router import get_eval_store_dep
from app.routers.studio_knowledge_router import get_agent_lookup_dep, get_studio_knowledge_store_dep
from app.stores.studio_definitions import SectionInput
from app.stores.studio_eval_runs import FakeEvalRunWriter
from app.stores.studio_evals import FakeEvalStore
from app.stores.studio_knowledge import FakeStudioKnowledgeStore
from app.studio.wiring import get_eval_judge_dep, get_eval_run_writer_dep
from tests.routers.conftest import (  # noqa: F401 — `agents_client` is a fixture
    DEFAULT_ORG_ID,
    DEFAULT_USER_ID,
    agents_client,
    seed_org_role,
)
from tests.studio.rt.fakes import DefinitionsAgentLookup, FakeStudioStore, ScriptedJudge

_MISSING = object()


class RtHarness:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.stores = client.stores
        self.org_id: UUID = DEFAULT_ORG_ID
        self.user_id: UUID = DEFAULT_USER_ID
        self.studio = FakeStudioStore()
        self.knowledge = FakeStudioKnowledgeStore()
        self.evals = FakeEvalStore()
        self.runs = FakeEvalRunWriter(self.evals)
        self.judge = ScriptedJudge()

    # HTTP passthrough
    def get(self, url, **kw):
        return self.client.get(url, **kw)

    def post(self, url, **kw):
        return self.client.post(url, **kw)

    def put(self, url, **kw):
        return self.client.put(url, **kw)

    def make_agent(
        self,
        key: str = "isa",
        *,
        nome: str = "Isa",
        ativo: bool = True,
        publish: bool = True,
        secoes: list[tuple[str, str, str]] | None = None,
        skills: list[dict[str, Any]] | None = None,
        tool_policy: dict[str, Any] | None = None,
    ):
        """A studio agent with a draft (optionally published as v1)."""
        store = self.studio
        agent = store.create_studio_agent(self.org_id, key, nome, None)
        if ativo:
            agent = store.update_agent(self.org_id, key, {"ativo": True})
        draft = store.create_draft(self.org_id, agent.id, None, self.user_id)
        if tool_policy is not None:
            store.update_draft(self.org_id, draft.id, {"tool_policy": tool_policy})
        secoes = secoes or [("identidade", "Identidade", "Você é a assistente de conteúdo.")]
        store.replace_sections(
            self.org_id, draft.id,
            [SectionInput(chave=c, titulo=t, ordem=i * 10, conteudo=body) for i, (c, t, body) in enumerate(secoes)],
        )
        for sk in skills or []:
            rec = store.create_skill(
                self.org_id, draft.id, nome=sk["nome"], descricao=sk.get("descricao", "Uma skill."),
                corpo=sk.get("corpo", "Passos da skill."), ordem=sk.get("ordem", 0), ativo=sk.get("ativo", True),
            )
            for caminho, conteudo in (sk.get("arquivos") or {}).items():
                store.upsert_skill_file(self.org_id, rec.id, caminho=caminho, titulo=None, conteudo=conteudo)
        version = store.get_version(self.org_id, draft.id)
        if publish:
            version = store.publish_version(self.org_id, draft.id, self.user_id, None, "publicação de teste do BE-RT")
        return store.get_agent(self.org_id, key), version


@pytest.fixture
def rt(agents_client):
    from app.main import app

    h = RtHarness(agents_client)
    bindings = {
        get_studio_definition_store_dep: lambda: h.studio,
        get_studio_knowledge_store_dep: lambda: h.knowledge,
        get_eval_store_dep: lambda: h.evals,
        get_agent_lookup_dep: lambda: DefinitionsAgentLookup(h.studio),
        get_eval_run_writer_dep: lambda: h.runs,
        get_eval_judge_dep: lambda: h.judge,
    }
    saved = {k: app.dependency_overrides.get(k, _MISSING) for k in bindings}
    app.dependency_overrides.update(bindings)
    seed_org_role(agents_client, role="owner")
    try:
        yield h
    finally:
        for k, v in saved.items():
            if v is _MISSING:
                app.dependency_overrides.pop(k, None)
            else:
                app.dependency_overrides[k] = v
