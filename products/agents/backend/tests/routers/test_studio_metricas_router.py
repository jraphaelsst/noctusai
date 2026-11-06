"""``/api/studio/agents/{key}/metricas*``: platform admin ONLY (strict 401 / 403), shapes, the origem filter."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.dependencies import get_auth_context, get_turn_metrics_store_dep
from app.routers.studio_agents_router import get_studio_definition_store_dep
from app.stores.studio_definitions import FakeStudioDefinitionStore
from app.stores.turn_metrics import FakeTurnMetricsStore
from noctusai_lib.api.auth.session import AuthContext
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

BASE = "/api/studio/agents/julia/metricas"
THREAD = uuid4()
PATHS = [BASE, f"{BASE}/turnos", f"{BASE}/threads", f"{BASE}/threads/{THREAD}"]


def _linha(origem="canal", thread=None, custo=0.01, **kw):
    return {
        "org_id": DEFAULT_ORG_ID, "agent_id": uuid4(), "agent_key": "julia", "version_id": None, "compiled_hash": "h1",
        "thread_id": thread, "origem": origem, "status": "ok", "handoff": False, "tools": [], "llm_calls": 1,
        "tokens_entrada": 1000, "tokens_saida": 10, "tokens_cache_leitura": 900, "tokens_cache_escrita": 0,
        "custo_usd": custo, "turno_ms": 1800, "llm_ms": 1700, "tool_ms": 0, "inbound_bytes": 30, "reply_bytes": 200,
        "prompt_bytes": 5000, "db_bytes": 230, **kw,
    }


@pytest.fixture
def kit(agents_client):
    from app.main import app

    metricas, studio = FakeTurnMetricsStore(), FakeStudioDefinitionStore()
    studio.create_studio_agent(DEFAULT_ORG_ID, "julia", "Julia", None, runtime="llm", owner_product="social-wiring")
    for r in (_linha(thread=THREAD), _linha(thread=THREAD, custo=0.03), _linha(origem="eval", custo=9.0)):
        metricas.registrar(r)
    ov = {get_turn_metrics_store_dep: lambda: metricas, get_studio_definition_store_dep: lambda: studio}
    app.dependency_overrides.update(ov)
    agents_client.metricas = metricas
    try:
        yield agents_client
    finally:
        for d in ov:
            app.dependency_overrides.pop(d, None)


def _admin(c, role="admin"):
    c.mock_supabase.set_table_data("noctus_users", [{
        "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "role": role, "org_role": "owner"}])


@pytest.mark.parametrize("path", PATHS)
def test_no_credential_is_401(kit, path):
    assert kit.raw().get(path).status_code == 401


@pytest.mark.parametrize("path", PATHS)
def test_org_owner_who_is_not_platform_admin_is_403(kit, path):
    _admin(kit, role="user")
    resp = kit.get(path)
    assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required"


@pytest.mark.parametrize("path", PATHS)
def test_product_token_is_403(kit, path):
    from app.main import app

    app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=["*"], raw_token="x", api_token_id=UUID(int=1))
    try:
        assert kit.raw().get(path).status_code == 403
    finally:
        app.dependency_overrides.pop(get_auth_context, None)


def test_summary_excludes_eval_by_default_and_has_the_contract_keys(kit):
    _admin(kit)
    body = kit.get(BASE).json()
    assert set(body) == {"agent_key", "janela", "origem", "org_id", "truncado", "resumo", "serie_diaria", "por_versao", "por_org"}
    assert body["origem"] == "canal" and body["resumo"]["turnos"] == 2 and body["resumo"]["custo_usd"] == 0.04
    assert len(body["serie_diaria"]) == 1


def test_origem_eval_and_todos(kit):
    _admin(kit)
    assert kit.get(BASE, params={"origem": "eval"}).json()["resumo"]["turnos"] == 1
    assert kit.get(BASE, params={"origem": "todos"}).json()["resumo"]["turnos"] == 3
    assert kit.get(BASE, params={"origem": "x"}).status_code == 422


def test_window_outside_the_data_is_empty(kit):
    _admin(kit)
    ate = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    assert kit.get(BASE, params={"ate": ate}).json()["resumo"]["turnos"] == 0


def test_turns_are_paginated_newest_first_with_the_three_blocks(kit):
    _admin(kit)
    body = kit.get(f"{BASE}/turnos", params={"limite": 1, "pagina": 2}).json()
    assert set(body) == {"agent_key", "janela", "origem", "org_id", "truncado", "total", "pagina", "limite", "itens"}
    assert body["total"] == 2 and len(body["itens"]) == 1
    assert set(body["itens"][0]) >= {"llm", "velocidade", "tamanho"}


def test_thread_views(kit):
    _admin(kit)
    lista = kit.get(f"{BASE}/threads").json()
    assert lista["total"] == 1 and lista["itens"][0]["thread_id"] == str(THREAD) and lista["itens"][0]["turnos"] == 2
    uma = kit.get(f"{BASE}/threads/{THREAD}").json()
    assert set(uma) == {"agent_key", "thread_id", "origem", "truncado", "resumo", "turnos"} and len(uma["turnos"]) == 2


def test_unknown_agent_is_404(kit):
    _admin(kit)
    assert kit.get("/api/studio/agents/nao-existe/metricas").status_code == 404
