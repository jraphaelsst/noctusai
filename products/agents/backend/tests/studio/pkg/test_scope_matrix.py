"""The scope-enforcement matrix (Agent Packages §A8, §I, §J3).

A `pk_*` product token is accepted ONLY on the routes whose scope it holds —
`packages:read`, `project-knowledge:write`, `learnings:write`/`learnings:read`.
Every other business route of the product keeps refusing a product caller with
403 `user_required`, EVEN WHEN the token holds every package scope. The set of
token-reachable routes is derived from the live route table (never a hand
list), so a new route can never silently become token-reachable.
"""
from __future__ import annotations

import re
from uuid import UUID

import pytest

from app.dependencies import PACKAGE_TOKEN_SCOPES
from tests.studio.pkg.conftest import make_bundle

ALL = tuple(sorted(PACKAGE_TOKEN_SCOPES))

#: (METHOD, path template) — the ONLY business routes a scoped token reaches.
TOKEN_ROUTES = {
    ("GET", "/api/agent-packages/{key}/versions"): "packages:read",
    ("GET", "/api/agent-packages/{key}/{versao}"): "packages:read",
    ("PUT", "/api/studio/agents/{key}/projects/{slug}/sources"): "project-knowledge:write",
    ("POST", "/api/studio/agents/{key}/learnings"): "learnings:write",
    ("GET", "/api/studio/agents/{key}/learnings"): "learnings:read",
}

#: `studio:publish` (2026-10-03, the noc pre-push publish leg): token-reachable
#: too, but only for a dev-advisor agent — pinned in `test_publish_scope.py`.
PUBLISH_ROUTES = {
    ("POST", "/api/studio/agents/{key}/import"),
    ("POST", "/api/studio/agents/{key}/evals/runs"),
    ("GET", "/api/studio/agents/{key}/evals/runs"),
    ("GET", "/api/studio/agents/{key}/evals/runs/{run_id}"),
    ("POST", "/api/studio/agents/{key}/draft/publish"),
}

#: Julia v2 content API (2026-10-19): token-reachable ONLY with the dedicated `studio:content-write`
#: scope (the `noctus.agents.content` MCP path) — never with a package/publish scope. Pinned in
#: `tests/studio/def/test_studio_conteudo_router.py` (a token without it is `scope_missing`).
CONTENT_WRITE_ROUTES = {
    ("PUT", "/api/studio/agents/{key}/draft/textos"),
    ("PUT", "/api/studio/agents/{key}/draft/ferramentas"),
    ("PUT", "/api/studio/agents/{key}/draft/decisoes"),
    ("PUT", "/api/studio/agents/{key}/draft/specs"),
    # the same MCP tool also writes the sections and the library pins, and reads the draft + content rows
    # to show a diff before it writes (A-SKILLS); the library itself (/api/skills-biblioteca) is outside
    # BUSINESS_PREFIXES and pinned in tests/studio/def/test_skills_biblioteca_router.py.
    ("PUT", "/api/studio/agents/{key}/draft/sections"),
    ("GET", "/api/studio/agents/{key}/draft"),
    ("GET", "/api/studio/agents/{key}/versions/{version_id}/textos"),
    ("GET", "/api/studio/agents/{key}/versions/{version_id}/ferramentas"),
    ("GET", "/api/studio/agents/{key}/versions/{version_id}/decisoes"),
    ("GET", "/api/studio/agents/{key}/versions/{version_id}/specs"),
    ("GET", "/api/studio/agents/{key}/draft/skills-biblioteca"),
    ("PUT", "/api/studio/agents/{key}/draft/skills-biblioteca/{skill}"),
    ("DELETE", "/api/studio/agents/{key}/draft/skills-biblioteca/{skill}"),
    ("GET", "/api/studio/agents/{key}/versions/{version_id}/skills-biblioteca"),
    # A-polish #3: kinds evals_mecanismo / conformidade_regras (pinned in tests/studio/def/test_a_rt2_ui_backend.py,
    # TestMcpContentKindsBackend: platform issuer only, audited, the definition's own row only)
    ("GET", "/api/studio/agents/{key}/evals/cases"),
    ("POST", "/api/studio/agents/{key}/evals/cases"),
    ("PATCH", "/api/studio/agents/{key}/evals/cases/{case_id}"),
    ("GET", "/api/studio/agents/{key}/conformidade/regras"),
    ("GET", "/api/studio/agents/{key}/conformidade/regras/{regra}"),
    ("PUT", "/api/studio/agents/{key}/conformidade/regras/{regra}"),
    # agent lifecycle (S1): the same MCP tool creates the EMPTY platform definition of a registered key
    ("POST", "/api/studio/plataforma/agents"),
    ("GET", "/api/studio/plataforma/agents/{key}"),
    ("PATCH", "/api/studio/plataforma/agents/{key}"),
    # 050 org-config isolation: the grant is the ONLY way a closed definition reaches one org
    ("GET", "/api/studio/plataforma/agents/{key}/grants"),
    ("POST", "/api/studio/plataforma/agents/{key}/grants"),
    # S3a: AI-generated first drafts (the UI and the chat use the SAME routes)
    ("POST", "/api/studio/agents/{key}/geracoes"),
    ("GET", "/api/studio/agents/{key}/geracoes"),
    ("GET", "/api/studio/agents/{key}/geracoes/{geracao_id}"),
    ("POST", "/api/studio/agents/{key}/geracoes/{geracao_id}/areas/{area}/repetir"),
    ("POST", "/api/studio/agents/{key}/geracoes/{geracao_id}/cancelar"),
}

#: Deleting an agent: reachable ONLY with the dedicated `studio:agent-delete` scope (minted with
#: `permitir_exclusao`), never with a package/publish/content scope. Pinned in
#: `tests/studio/def/test_agent_delete_router.py`.
AGENT_DELETE_ROUTES = {("DELETE", "/api/studio/agents/{key}")}

#: Prefixes of the product's business API. `/api/auth`, `/api/settings/api-tokens`
#: (the seed's own auth surface, with its own human-only rules) and health are out.
BUSINESS_PREFIXES = (
    "/api/studio", "/api/agents", "/api/conversations", "/api/approvals", "/api/persona",
    "/api/admin", "/api/agent-packages",
)


def _business_routes():
    from app.main import app

    seen = set()
    for r in app.routes:
        path = getattr(r, "path", "")
        if not path.startswith(BUSINESS_PREFIXES):
            continue
        for method in sorted(getattr(r, "methods", None) or ()):
            if method in ("HEAD", "OPTIONS"):
                continue
            seen.add((method, path))
    return sorted(seen)


def _fill(path: str) -> str:
    return re.sub(r"\{[^}/]+\}", lambda m: str(UUID(int=1)) if m.group(0).endswith("id}") else "x", path)


def test_the_matrix_actually_covers_the_product(pkg):
    routes = _business_routes()
    assert len(routes) > 60, "route discovery found too few routes — the matrix would be vacuous"
    assert set(TOKEN_ROUTES) | PUBLISH_ROUTES | CONTENT_WRITE_ROUTES | AGENT_DELETE_ROUTES <= set(routes)


@pytest.mark.parametrize("method,path", [r for r in _business_routes() if r not in TOKEN_ROUTES and r not in PUBLISH_ROUTES and r not in CONTENT_WRITE_ROUTES and r not in AGENT_DELETE_ROUTES])
def test_every_other_route_refuses_a_fully_scoped_token_with_user_required(pkg, method, path):
    with pkg.as_token(*ALL):
        resp = pkg.rt.client.raw().request(method, _fill(path), json={})
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code} {resp.text[:200]}"
    detail = resp.json()
    code = detail.get("code") or (detail.get("detail") or {}).get("code") if isinstance(detail, dict) else None
    assert code in ("user_required", "platform_admin_required"), f"{method} {path}: {detail}"


def test_a_fully_scoped_package_token_cannot_delete_an_agent(pkg):
    with pkg.as_token(*ALL):
        resp = pkg.rt.client.raw().request("DELETE", "/api/studio/agents/x")
    assert resp.status_code == 403 and resp.json().get("code") == "scope_missing", resp.text[:200]


#: A concrete URL + body per token route (the agent imported by `pkg.advisor()`).
_CALLS = {
    ("GET", "/api/agent-packages/{key}/versions"): ("/api/agent-packages/mobile-dev/versions", None),
    ("GET", "/api/agent-packages/{key}/{versao}"): ("/api/agent-packages/mobile-dev/0.1.0", None),
    ("PUT", "/api/studio/agents/{key}/projects/{slug}/sources"): (
        "/api/studio/agents/mobile-dev/projects/limiar-app/sources", []),
    ("POST", "/api/studio/agents/{key}/learnings"): (
        "/api/studio/agents/mobile-dev/learnings",
        {"project_slug": "limiar-app", "rows": [{"data": "2026-10-03", "tipo": "pitfall", "texto": "x"}]}),
    ("GET", "/api/studio/agents/{key}/learnings"): ("/api/studio/agents/mobile-dev/learnings", None),
}


def test_every_token_route_has_a_concrete_call():
    assert set(_CALLS) == set(TOKEN_ROUTES)


@pytest.mark.parametrize("method,path", sorted(TOKEN_ROUTES))
def test_each_token_route_demands_exactly_its_scope(pkg, method, path):
    pkg.advisor()
    needed = TOKEN_ROUTES[(method, path)]
    others = tuple(s for s in ALL if s != needed)
    url, body = _CALLS[(method, path)]
    kwargs = {} if body is None else {"json": body}
    with pkg.as_token(*others):
        denied = pkg.rt.client.raw().request(method, url, **kwargs)
    assert denied.status_code == 403
    assert denied.json()["code"] == "scope_missing"
    with pkg.as_token(needed):
        allowed = pkg.rt.client.raw().request(method, url, **kwargs)
    assert allowed.status_code == 200, f"{method} {url}: {allowed.status_code} {allowed.text[:200]}"


def test_the_documented_scope_set_is_exactly_the_five_the_routes_use():
    assert PACKAGE_TOKEN_SCOPES == set(TOKEN_ROUTES.values()) | {"studio:publish"}


class TestExistingSurfacesUnchanged:
    """Bia and IsaIA keep their Studio contract: shapes + auth as before."""

    def test_a_runtime_import_without_any_c4_key_still_works_and_is_runtime(self, pkg):
        body = make_bundle(agente__kind="runtime")
        body["agente"].pop("kind")
        body["versao"].pop("versao_semver")
        body["versao"].pop("package_sha")
        body.pop("claude")
        resp = pkg.import_bundle(body)
        assert resp.status_code == 200, resp.text
        assert resp.json()["pacote"] is None
        assert pkg.get("/api/studio/agents/mobile-dev").json()["kind"] == "runtime"

    def test_bia_keeps_its_listing_shape_and_is_a_runtime_agent(self, pkg):
        resp = pkg.get("/api/studio/agents")
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["kind"] == "runtime"
