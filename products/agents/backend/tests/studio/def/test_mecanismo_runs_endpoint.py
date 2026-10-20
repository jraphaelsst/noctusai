"""POST /api/studio/agents/{key}/draft/mecanismo-runs (Julia v2 A-EVAL): platform admin only, driver injectable.

A-RT2: the trigger is ASYNC -- 202 + a run id, the suite executes in a background task, and
``GET .../mecanismo-runs/{id}`` reports ``executando`` / ``concluida`` / ``falhou`` (codes only)."""
from __future__ import annotations

import asyncio
import time
from uuid import UUID, uuid4

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


def _poll(studio, run_id, *, timeout=10.0):
    """Wait (the task runs on the entered client's portal) until the run leaves ``executando``."""
    fim = time.monotonic() + timeout
    while True:
        body = studio.get(f"{BASE}/isa/mecanismo-runs/{run_id}").json()
        if body["status"] != "executando" or time.monotonic() > fim:
            return body
        time.sleep(0.02)


def _run(studio):
    """Trigger and wait: the finished run's state."""
    resp = studio.post(URL)
    assert resp.status_code == 202, resp.text
    return _poll(studio, resp.json()["run_id"])


class _Lento(_Live):
    async def executar_turno(self, thread, mensagem_lead):
        await asyncio.sleep(0.4)
        return await super().executar_turno(thread, mensagem_lead)


def _setup(studio, *, driver, cases=1):
    studio.raw.__enter__()  # ONE portal for the whole test: the background run outlives the POST (as under uvicorn)
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
    assert resp.status_code == 202, resp.text
    assert set(resp.json()) == {"run_id", "compiled_hash", "driver", "status"} and resp.json()["status"] == "executando"
    body = _poll(studio, resp.json()["run_id"])
    assert body["status"] == "concluida" and body["aprovado"] and body["completo"] and body["driver"] == "live"
    assert body["casos"][0]["slug"] == "m0" and [e["status"] for e in body["casos"][0]["execucoes"]] == ["aprovado", "aprovado"]
    run = store.runs[UUID(body["run_id"])]
    assert run["compiled_hash"] == body["compiled_hash"] and run["driver"] == "live" and run["limite_usd"] == 5.0


def test_failures_are_reported_as_assert_and_code(studio):
    _setup(studio, driver=_Live([TurnOutcome(bolhas=("segredo do prompt",), estado=Estado(estagio="novo"))]))
    body = _run(studio)
    assert not body["aprovado"]
    assert body["casos"][0]["execucoes"][0]["falhas"] == [{"assert": "estagio_final", "codigo": "esperado:visita|obtido:novo"}]
    assert "segredo" not in str(body)


def test_an_agent_without_mecanismo_cases_is_409(studio):
    _setup(studio, driver=_Live(_ok()), cases=0)
    resp = studio.post(URL)
    assert resp.status_code == 409 and resp.json()["code"] == "sem_casos_mecanismo"


def test_a_fake_driver_run_is_stamped_fake_and_cannot_open_the_gate(studio):
    store = _setup(studio, driver=FakeEvalTurnDriver(_ok()))
    body = _run(studio)
    assert body["driver"] == "fake" and store.runs[UUID(body["run_id"])]["driver"] == "fake"


class TestPoll:
    def test_unauthenticated_is_401_and_org_roles_are_403(self, studio):
        _setup(studio, driver=_Live(_ok()))
        poll = f"{BASE}/isa/mecanismo-runs/{uuid4()}"
        assert studio.raw.get(poll).status_code == 401
        studio.as_org_admin_only()
        r = studio.get(poll)
        assert r.status_code == 403 and r.json()["code"] == "platform_admin_required"
        studio.as_role("member")
        assert studio.get(poll).status_code == 403

    def test_an_unknown_run_is_404(self, studio):
        _setup(studio, driver=_Live(_ok()))
        assert studio.get(f"{BASE}/isa/mecanismo-runs/{uuid4()}").status_code == 404

    def test_a_run_of_another_agent_is_404(self, studio):
        _setup(studio, driver=_Live(_ok()))
        rid = studio.post(URL).json()["run_id"]
        _poll(studio, rid)
        assert studio.post(BASE, json={"key": "outra", "nome": "Outra"}).status_code == 201
        assert studio.get(f"{BASE}/outra/mecanismo-runs/{rid}").status_code == 404

    def test_the_run_is_reported_executando_then_concluida(self, studio):
        _setup(studio, driver=_Lento(_ok()))
        rid = studio.post(URL).json()["run_id"]
        primeiro = studio.get(f"{BASE}/isa/mecanismo-runs/{rid}").json()
        assert primeiro["status"] == "executando" and primeiro["casos"] == [] and primeiro["aprovado"] is False
        fim = _poll(studio, rid)
        assert fim["status"] == "concluida" and fim["aprovado"] and fim["total_casos"] == 1 and fim["casos_aprovados"] == 1

    def test_a_second_run_while_one_executes_is_409_run_in_progress(self, studio):
        _setup(studio, driver=_Lento(_ok()))
        rid = studio.post(URL).json()["run_id"]
        again = studio.post(URL)
        assert again.status_code == 409 and again.json()["code"] == "run_in_progress"
        assert _poll(studio, rid)["status"] == "concluida"

    def test_a_crashing_driver_marks_the_run_falhou_with_a_fixed_text(self, studio):
        class _Quebra(_Live):
            async def executar_turno(self, thread, mensagem_lead):
                raise BaseException("segredo-do-prompt")  # noqa: B904 -- not an Exception: escapes the runner's per-turn guard

        _setup(studio, driver=_Quebra(_ok()))
        rid = studio.post(URL).json()["run_id"]
        body = _poll(studio, rid)
        assert body["status"] == "falhou" and body["aprovado"] is False
        assert "segredo" not in str(body) and body["erro"]


def test_the_versions_endpoint_summarises_the_latest_run_for_the_current_hash(studio):
    _setup(studio, driver=_Live(_ok()))
    draft_id = studio.store.get_draft(studio.org_id, UUID(studio.get(f"{BASE}/isa").json()["id"])).id
    assert studio.get(f"{BASE}/isa/versions/{draft_id}").json()["mecanismo"] is None
    run = _run(studio)
    resumo = studio.get(f"{BASE}/isa/versions/{draft_id}").json()["mecanismo"]
    assert resumo["run_id"] == run["run_id"] and resumo["driver"] == "live" and resumo["aprovado"] is True
    assert resumo["casos_total"] == 1 and resumo["casos_aprovados"] == 1
    # a content change moves the hash: the old run is no longer "for the current hash"
    assert studio.put(f"{BASE}/isa/draft/sections", json={"secoes": [
        {"chave": "identidade", "titulo": "Identidade", "ordem": 10, "conteudo": "Outra.", "ativo": True}]}).status_code == 200
    assert studio.get(f"{BASE}/isa/versions/{draft_id}").json()["mecanismo"] is None


class TestOrphanSweep:
    """Startup: runs a dead process left ``executando`` become ``falhou`` / ``interrompida`` and free the slot."""

    def _store(self):
        from app.stores.studio_eval_mecanismo import FakeMecanismoStore

        return FakeMecanismoStore(FakeEvalStore())

    def _start(self, store, version):
        return store.start_run(
            UUID(int=1), UUID(int=2), version, compiled_hash="h", driver="live", limite_usd=None,
            started_by=UUID(int=3), total_casos=1)

    def test_an_executing_run_from_before_boot_is_failed_with_the_fixed_text_and_frees_the_slot(self):
        from datetime import timedelta

        from app.stores._util import utcnow
        from app.studio.eval_mecanismo_service import ORFA_ERRO, varrer_runs_orfas

        store, v = self._store(), UUID(int=10)
        rid = self._start(store, v)
        with pytest.raises(Exception, match="already executing"):
            self._start(store, v)  # the unique slot is held
        assert varrer_runs_orfas(store, started_before=utcnow() + timedelta(seconds=1)) == 1
        run = store.get_run(UUID(int=1), rid)
        assert run["status"] == "falhou" and run["erro"] == ORFA_ERRO == "interrompida" and run["finished_at"] is not None
        assert self._start(store, v)  # freed

    def test_a_run_that_started_after_the_cutoff_and_a_finished_run_are_untouched(self):
        from datetime import timedelta

        from app.stores._util import utcnow
        from app.studio.eval_mecanismo_service import varrer_runs_orfas

        store = self._store()
        antigo, novo = self._start(store, UUID(int=11)), self._start(store, UUID(int=12))
        store.runs[antigo]["started_at"] = utcnow() - timedelta(hours=1)
        store.runs[novo]["status"] = "concluida"
        livre = self._start(store, UUID(int=13))
        assert varrer_runs_orfas(store, started_before=utcnow() - timedelta(minutes=5)) == 1
        assert store.get_run(UUID(int=1), antigo)["status"] == "falhou"
        assert store.get_run(UUID(int=1), novo)["status"] == "concluida"
        assert store.get_run(UUID(int=1), livre)["status"] == "executando"

    def test_nothing_to_sweep_is_zero(self):
        from app.studio.eval_mecanismo_service import varrer_runs_orfas

        assert varrer_runs_orfas(self._store()) == 0

    def test_the_app_startup_runs_the_sweep_step(self):
        import inspect

        from app import main

        src = inspect.getsource(main.on_startup)
        assert "fail_orphan_mecanismo_runs" in src and "varrer_runs_orfas" in src
