"""Owner decision (go-live hardening): Julia's core is editable ONLY by NoctusAI platform admins (or the platform content
token). A tenant org's owner/admin gets a strict 403 on every Studio WRITE; a platform admin passes the gate."""
from __future__ import annotations

import pytest

from app import dependencies as deps
from app.main import app

# (method, url) of the Studio writes an org admin used to reach. Bodies are irrelevant: auth answers first.
ESCRITAS = [
    ("POST", "/api/studio/agents"),
    ("PATCH", "/api/studio/agents/julia"),
    ("POST", "/api/studio/agents/julia/draft"),
    ("PATCH", "/api/studio/agents/julia/draft"),
    ("DELETE", "/api/studio/agents/julia/draft"),
    ("PUT", "/api/studio/agents/julia/draft/sections"),
    ("POST", "/api/studio/agents/julia/draft/skills"),
    ("PATCH", "/api/studio/agents/julia/draft/skills/00000000-0000-0000-0000-000000000001"),
    ("DELETE", "/api/studio/agents/julia/draft/skills/00000000-0000-0000-0000-000000000001"),
    ("PUT", "/api/studio/agents/julia/draft/textos"),
    ("PUT", "/api/studio/agents/julia/draft/ferramentas"),
    ("PUT", "/api/studio/agents/julia/draft/decisoes"),
    ("PUT", "/api/studio/agents/julia/draft/specs"),
    ("PUT", "/api/studio/agents/julia/specs"),
    ("POST", "/api/studio/agents/julia/draft/publish"),
    ("POST", "/api/studio/agents/julia/evals/cases"),
    ("POST", "/api/studio/agents/julia/evals/runs"),
]


def _chamar(studio, metodo, url):
    corpo = {} if metodo == "DELETE" else {"json": {}}
    return getattr(studio, metodo.lower())(url, **corpo)


@pytest.mark.parametrize("metodo,url", ESCRITAS)
def test_a_tenant_org_admin_gets_a_strict_403(studio, metodo, url):
    studio.as_org_admin_only("owner")
    resp = _chamar(studio, metodo, url)
    assert resp.status_code == 403, (metodo, url, resp.text)


@pytest.mark.parametrize("metodo,url", [e for e in ESCRITAS if e[1].endswith(("/draft", "/agents/julia"))])
def test_a_platform_admin_passes_the_gate(studio, metodo, url):
    resp = _chamar(studio, metodo, url)
    assert resp.status_code != 403, (metodo, url, resp.text)  # past auth (the body/agent may still be refused)


def test_no_studio_write_route_is_gated_by_an_org_level_dependency():
    """Static: walk every write route's dependency tree; none may use the org-level admin/member gates."""
    org_level = {deps.require_admin, deps.require_member, deps.require_admin_or_content_token}
    alvo = ("/api/studio/agents", "/api/studio/plataforma", "/api/agents/{key}/toggle")
    ofensores = []

    def chamadas(dep):
        yield dep.call
        for sub in dep.dependencies:
            yield from chamadas(sub)

    for r in app.routes:
        if not getattr(r, "dependant", None) or not set(r.methods or ()) & {"POST", "PUT", "PATCH", "DELETE"}:
            continue
        if not r.path.startswith(alvo):
            continue
        if any(c in org_level for c in chamadas(r.dependant)):
            ofensores.append((sorted(r.methods), r.path))
    assert not ofensores, ofensores
