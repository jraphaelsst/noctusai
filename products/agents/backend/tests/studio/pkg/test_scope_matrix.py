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
    assert set(TOKEN_ROUTES) <= set(routes)


@pytest.mark.parametrize("method,path", [r for r in _business_routes() if r not in TOKEN_ROUTES])
def test_every_other_route_refuses_a_fully_scoped_token_with_user_required(pkg, method, path):
    with pkg.as_token(*ALL):
        resp = pkg.rt.client.raw().request(method, _fill(path), json={})
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code} {resp.text[:200]}"
    detail = resp.json()
    code = detail.get("code") or (detail.get("detail") or {}).get("code") if isinstance(detail, dict) else None
    assert code in ("user_required", "platform_admin_required"), f"{method} {path}: {detail}"


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


def test_the_documented_scope_set_is_exactly_the_four_the_routes_use():
    assert PACKAGE_TOKEN_SCOPES == set(TOKEN_ROUTES.values())


class TestExistingSurfacesUnchanged:
    """Julia and IsaIA keep their Studio contract: shapes + auth as before."""

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

    def test_julia_keeps_its_listing_shape_and_is_a_runtime_agent(self, pkg):
        resp = pkg.get("/api/studio/agents")
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["kind"] == "runtime"
