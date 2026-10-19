"""Visibility tier 1 on EVERY studio router that serves an agent's definition, knowledge, clients or
eval material (owner mandate 2026-10-19, IP protection): platform admin only — strict 403
`platform_admin_required` for an org admin and a member, 401 unauthenticated. Routes that are reachable by
a SCOPED product token (publish / packages / learnings / project-knowledge) keep their own scope gates."""
from __future__ import annotations

import re
from uuid import UUID

import pytest
from fastapi.routing import APIRoute

from app.dependencies import require_platform_admin
from app.routers.studio_clients_router import router as clients
from app.routers.studio_conteudo_router import router as conteudo
from app.routers.studio_evals_router import router as evals
from app.routers.studio_knowledge_router import router as knowledge
from app.routers.studio_package_sync_router import router as package_sync
from app.routers.studio_agents_router import router as agents


def _uses_platform_admin(dependant) -> bool:
    return dependant.call is require_platform_admin or any(_uses_platform_admin(d) for d in dependant.dependencies)


def _fill(path: str) -> str:
    return re.sub(r"\{[^}/]+\}", lambda m: str(UUID(int=1)) if m.group(0).endswith("id}") else "x", path)


def _routes():
    out = []
    for r in (clients, knowledge, evals, package_sync, agents, conteudo):
        for route in r.routes:
            if isinstance(route, APIRoute) and _uses_platform_admin(route.dependant):
                for m in sorted(route.methods - {"HEAD", "OPTIONS"}):
                    out.append((m, route.path))
    return out


ROUTES = _routes()


def test_the_matrix_is_not_vacuous():
    assert len(ROUTES) > 35
    paths = {p for _, p in ROUTES}
    assert any("/knowledge" in p for p in paths) and any("/evals" in p for p in paths)
    assert any("/clients" in p for p in paths) and any("/prompts/" in p for p in paths)


@pytest.mark.parametrize("method,path", ROUTES)
def test_unauthenticated_is_401(studio, method, path):
    assert studio.raw.request(method, _fill(path), json={}).status_code == 401


@pytest.mark.parametrize("who", ["org_admin", "member"])
@pytest.mark.parametrize("method,path", ROUTES)
def test_org_admin_and_member_are_403_platform_admin_required(studio, who, method, path):
    studio.as_org_admin_only() if who == "org_admin" else studio.as_role("member")
    resp = getattr(studio, method.lower())(_fill(path), json={}) if method in ("POST", "PUT", "PATCH") else getattr(studio, method.lower())(_fill(path))
    assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"
    assert resp.json()["code"] == "platform_admin_required"
