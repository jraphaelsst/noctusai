"""POST /api/studio/agents/{key}/draft/mecanismo-runs (Julia v2 A-EVAL): platform admin only, driver injectable."""
from __future__ import annotations

from uuid import UUID

import pytest

from app.routers.studio_agents_router import get_mecanismo_store_dep
from app.stores.studio_eval_mecanismo import FakeMecanismoStore
from app.stores.studio_evals import EvalCaseInput, FakeEvalStore
from app.studio.eval_driver import Estado, FakeEvalTurnDriver, TurnOutcome, configure_eval_turn_driver, get_eval_turn_driver

BASE = "/api/studio/agents"
SECTIONS = {"secoes": [
    {"chave": "identidade", "titulo": "Identidade", "ordem": 10, "conteudo": "Você é estrategista.", "ativo": True},
    {"chave": "regras", "titulo": "Regras", "ordem": 20, "conteudo": "Seja direta.", "ativo": True},
]}
URL = f"{BASE}/isa/draft/mecanismo-runs"


class _Live(FakeEvalTurnDriver):
    tipo = "live"


def _setup(studio, *, driver, cases=1):
    assert studio.post(BASE, json={"key": "isa", "nome": "Isa"}).status_code == 201
    assert studio.put(f"{BASE}/isa/draft/sections", json=SECTIONS).status_code == 200
    agent_id = UUID(studio.get(f"{BASE}/isa").json()["id"])
    evals = FakeEvalStore()
    for i in range(cases):
        evals.create_case(studio.org_id, agent_id, EvalCaseInput(
            slug=f"m{i}", titulo="t", entrada="cenário sintético", criterios={}, suite="mecanismo", k=2,
            roteiro={"turnos": [{"lead": "quero comprar"}]}, asserts={"estagio_final": "visita"},
        ))
    store = FakeMecanismoStore(evals)
    app = studio.raw.app
    app.dependency_overrides[get_mecanismo_store_dep] = lambda: store
    app.dependency_overrides[get_eval_turn_driver] = lambda: driver
    return store


def _ok():
    return [TurnOutcome(bolhas=("ok",), estado=Estado(estagio="visita"))]


def test_unauthenticated_is_401(studio):
    assert studio.raw.post(URL).status_code == 401


@pytest.mark.parametrize("who", ["org_admin", "member"])
def test_org_admin_and_member_are_403_platform_admin_required(studio, who):
    _setup(studio, driver=_Live(_ok()))
    if who == "org_admin":
        studio.as_org_admin_only()
    else:
        studio.as_role("member")
    resp = studio.post(URL)
    assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required"


def test_no_adapter_configured_is_409_driver_indisponivel(studio):
    _setup(studio, driver=None)
    resp = studio.post(URL)
    assert resp.status_code == 409 and resp.json()["code"] == "driver_indisponivel"


def test_the_default_factory_is_not_configured():
    configure_eval_turn_driver(None)
    assert get_eval_turn_driver() is None
    configure_eval_turn_driver(lambda: _Live(_ok()))
    try:
        assert get_eval_turn_driver().tipo == "live"
    finally:
        configure_eval_turn_driver(None)


def test_a_run_is_executed_recorded_and_reported_as_codes_only(studio):
    store = _setup(studio, driver=_Live(_ok()))
    resp = studio.post(URL)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["aprovado"] and body["completo"] and body["driver"] == "live"
    assert body["casos"][0]["slug"] == "m0" and [e["status"] for e in body["casos"][0]["execucoes"]] == ["aprovado", "aprovado"]
    run = store.runs[UUID(body["run_id"])]
    assert run["compiled_hash"] == body["compiled_hash"] and run["driver"] == "live" and run["limite_usd"] == 5.0


def test_failures_are_reported_as_assert_and_code(studio):
    _setup(studio, driver=_Live([TurnOutcome(bolhas=("segredo do prompt",), estado=Estado(estagio="novo"))]))
    body = studio.post(URL).json()
    assert not body["aprovado"]
    assert body["casos"][0]["execucoes"][0]["falhas"] == [{"assert": "estagio_final", "codigo": "esperado:visita|obtido:novo"}]
    assert "segredo" not in str(body)


def test_an_agent_without_mecanismo_cases_is_409(studio):
    _setup(studio, driver=_Live(_ok()), cases=0)
    resp = studio.post(URL)
    assert resp.status_code == 409 and resp.json()["code"] == "sem_casos_mecanismo"


def test_a_fake_driver_run_is_stamped_fake_and_cannot_open_the_gate(studio):
    store = _setup(studio, driver=FakeEvalTurnDriver(_ok()))
    body = studio.post(URL).json()
    assert body["driver"] == "fake" and store.runs[UUID(body["run_id"])]["driver"] == "fake"
