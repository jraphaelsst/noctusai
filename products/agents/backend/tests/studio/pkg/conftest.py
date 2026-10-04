"""Fixtures for the Agent Packages suite (BE-API slice).

Builds on the BE-RT ``rt`` harness (the REAL app with every studio store on a
shared Fake) and adds the package store seam + a context manager that makes
the request run as a ``pk_*`` product token with chosen scopes — through
``app.dependency_overrides[get_auth_context]``, the same seam the credentials
suite uses; never a patch of our own guard.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID

import pytest

from app.dependencies import get_auth_context
from app.routers.studio_package_sync_router import get_agent_package_store_dep
from app.stores.agent_packages import FakeAgentPackageStore
from noctusai_lib.api.auth.session import AuthContext
from tests.routers.conftest import DEFAULT_ORG_ID, agents_client  # noqa: F401 — fixture
from tests.studio.rt.conftest import RtHarness, rt  # noqa: F401 — fixtures

_MISSING = object()

SHA = "a" * 64
OTHER_ORG = UUID(int=987654321)

TREE = [
    {"caminho": ".claude/agents/mobile-dev.md", "conteudo": "---\nname: mobile-dev\n---\nCorpo.\n"},
    {"caminho": "agents/mobile-dev/PACKAGE.json",
     "conteudo": '{"key": "mobile-dev", "versao": "0.1.0", "sha": "%s", "compiled_hash": "h1", "built_at": "2026-10-03T00:00:00Z"}\n' % SHA},
    {"caminho": "agents/mobile-dev/LEARNINGS.md", "conteudo": "| Data | Tipo | Aprendizado | Evidência | Status |\n|---|---|---|---|---|\n"},
]

BUNDLE: dict[str, Any] = {
    "formato": "noctus.agent-bundle/v1",
    "agente": {"key": "mobile-dev", "nome": "Mobile dev", "descricao": "Advisor de mobile.", "kind": "dev-advisor"},
    "versao": {"notas": "0.1.0", "model": "claude-sonnet-5", "effort": "medium", "max_turns": 30, "idioma": "en",
               "tool_policy": {"web_search": False, "knowledge": True},
               "versao_semver": "0.1.0", "package_sha": SHA},
    "secoes": [{"chave": "identidade", "titulo": "Identity", "ordem": 10, "conteudo": "You advise on mobile apps.", "ativo": True}],
    "skills": [],
    "conhecimento": [],
    "evals": [{"slug": "basico", "titulo": "Basico", "entrada": "Como faço X?", "contexto": None,
               "criterios": {"deve": ["responder"], "nao_deve": []}, "rubrica": None, "tags": []}],
    "clientes": [],
    "claude": [{"caminho": f["caminho"], "conteudo": f["conteudo"]} for f in TREE],
}


def make_bundle(**changes: Any) -> dict[str, Any]:
    body = copy.deepcopy(BUNDLE)
    for dotted, value in changes.items():
        node = body
        *parents, leaf = dotted.split("__")
        for p in parents:
            node = node[p]
        if value is _MISSING:
            node.pop(leaf, None)
        else:
            node[leaf] = value
    return body


class PkgHarness:
    def __init__(self, rt_: RtHarness) -> None:
        self.rt = rt_
        self.packages = FakeAgentPackageStore()

    # passthrough to the user-authenticated client
    def get(self, url, **kw):
        return self.rt.get(url, **kw)

    def post(self, url, **kw):
        return self.rt.post(url, **kw)

    def put(self, url, **kw):
        return self.rt.put(url, **kw)

    def patch(self, url, **kw):
        return self.rt.client.patch(url, **kw)

    def import_bundle(self, body: dict[str, Any] | None = None, *, key: str = "mobile-dev"):
        return self.rt.post(f"/api/studio/agents/{key}/import", json=body or BUNDLE)

    def publish_imported(self, key: str = "mobile-dev"):
        """Publish the draft the import left (override reason, as the BE-RT tests do)."""
        agent = self.rt.studio.get_agent(self.rt.org_id, key)
        draft = self.rt.studio.get_draft(self.rt.org_id, agent.id)
        version = self.rt.publish(agent, draft.id)
        return agent, version

    def advisor(self, key: str = "mobile-dev", *, publish: bool = True):
        assert self.import_bundle(make_bundle(agente__key=key), key=key).status_code == 200
        return self.publish_imported(key) if publish else (self.rt.studio.get_agent(self.rt.org_id, key), None)

    @contextmanager
    def as_token(self, *scopes: str, org_id: UUID = DEFAULT_ORG_ID) -> Iterator[None]:
        from app.main import app

        saved = app.dependency_overrides.get(get_auth_context, _MISSING)
        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            org_id=org_id, caller_kind="product", user_id=None, scopes=list(scopes),
            raw_token="pk_test", api_token_id=UUID(int=7),
        )
        try:
            yield
        finally:
            if saved is _MISSING:
                app.dependency_overrides.pop(get_auth_context, None)
            else:
                app.dependency_overrides[get_auth_context] = saved


@pytest.fixture
def pkg(rt):
    from app.main import app

    h = PkgHarness(rt)
    saved = app.dependency_overrides.get(get_agent_package_store_dep, _MISSING)
    app.dependency_overrides[get_agent_package_store_dep] = lambda: h.packages
    try:
        yield h
    finally:
        if saved is _MISSING:
            app.dependency_overrides.pop(get_agent_package_store_dep, None)
        else:
            app.dependency_overrides[get_agent_package_store_dep] = saved
