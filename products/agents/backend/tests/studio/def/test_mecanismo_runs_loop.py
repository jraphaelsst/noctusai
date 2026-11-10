"""The mechanism suite inside an eval loop (gate G1-G7): ``POST .../draft/mecanismo-runs?loop_id=`` books the run as a round,
refuses on G6/G7, and closes the round (stop + notify) when the background run ends."""
from __future__ import annotations

import importlib
from uuid import UUID, uuid4

from app.notifications import FakeNotificationSink
from app.routers.studio_agents_router import get_loop_service_dep
from app.stores.studio_eval_consolidacao import FakeConsolidacaoStore
from app.stores.studio_eval_loops import FakeLoopStore
from app.studio.eval_driver import Estado, TurnOutcome
from app.studio.eval_loop_service import EvalLoopService
_base = importlib.import_module("tests.studio.def.test_mecanismo_runs_endpoint")  # `def` is a keyword: no plain import
BASE, URL, _Live, _ok, _poll, _setup = _base.BASE, _base.URL, _base._Live, _base._ok, _base._poll, _base._setup


def _loop(studio, *, suite="mecanismo", orcamento=20.0):
    loops, sink = FakeLoopStore(), FakeNotificationSink(admin_ids=["owner"])
    svc = EvalLoopService(loops, sink, FakeConsolidacaoStore())
    studio.raw.app.dependency_overrides[get_loop_service_dep] = lambda: svc
    agent_id = UUID(studio.get(f"{BASE}/isa").json()["id"])
    rec = loops.create_loop(studio.org_id, agent_id, agente_chave="isa", suite=suite, rodadas_planejadas=10, alvo=1.0, piso=0.8,
                            orcamento_usd=orcamento, started_by=uuid4())
    return svc, loops, sink, agent_id, rec


def _start(studio, loop_id):
    return studio.post(f"{URL}?loop_id={loop_id}")


def test_a_passing_round_at_100_percent_concludes_the_loop_and_notifies(studio):
    _setup(studio, driver=_Live(_ok()))
    svc, loops, sink, agent_id, rec = _loop(studio)
    resp = _start(studio, rec.id)
    assert resp.status_code == 202, resp.text
    body = _poll(studio, resp.json()["run_id"])
    assert body["status"] == "concluida"
    e = svc.estado(studio.org_id, agent_id, rec.id)
    assert e["status"] == "concluido" and e["motivo_parada"] == "alvo_atingido" and e["serie"][0]["score"] == 1.0
    assert sink.sent and sink.sent[0]["metadata"]["motivo"] == "alvo_atingido"
    assert loops.runs[("mecanismo", UUID(resp.json()["run_id"]))] == rec.id  # loop_id mirrored on the run


def test_a_failing_round_is_recorded_with_its_failing_cases_and_an_unchanged_hash_is_refused(studio):
    _setup(studio, driver=_Live([TurnOutcome(bolhas=("x",), estado=Estado(estagio="novo"))]))
    svc, _, sink, agent_id, rec = _loop(studio)
    resp = _start(studio, rec.id)
    assert resp.status_code == 202, resp.text
    _poll(studio, resp.json()["run_id"])
    e = svc.estado(studio.org_id, agent_id, rec.id)
    assert e["status"] == "ativo" and e["serie"][0]["score"] == 0.0 and e["serie"][0]["falhas"] == ["m0"]
    again = _start(studio, rec.id)  # nothing was fixed: the same compiled hash
    assert again.status_code == 409 and again.json()["code"] == "hash_inalterado" and "m0" in again.json()["detail"]
    assert sink.sent == []


def test_the_loop_budget_clamps_the_run_cap_and_a_concluded_loop_refuses(studio):
    store = _setup(studio, driver=_Live(_ok()))
    _, _, _, _, rec = _loop(studio, orcamento=3.0)
    resp = _start(studio, rec.id)
    run = store.runs[UUID(resp.json()["run_id"])]
    assert run["limite_usd"] == 3.0  # min(settings 5.0, what the loop has left)
    _poll(studio, resp.json()["run_id"])  # 100%: the loop concluded
    refused = _start(studio, rec.id)
    assert refused.status_code == 409 and refused.json()["code"] == "loop_encerrado"


def test_a_loop_of_the_other_suite_is_422_and_an_unknown_loop_is_404(studio):
    _setup(studio, driver=_Live(_ok()))
    _, _, _, _, rec = _loop(studio, suite="comportamento")
    wrong = _start(studio, rec.id)
    assert wrong.status_code == 422 and wrong.json()["code"] == "loop_suite_invalida"
    assert _start(studio, uuid4()).status_code == 404 and _start(studio, uuid4()).json()["code"] == "loop_not_found"


def test_a_run_without_a_loop_is_unchanged(studio):
    _setup(studio, driver=_Live(_ok()))
    svc, loops, _, agent_id, rec = _loop(studio)
    resp = studio.post(URL)
    assert resp.status_code == 202
    _poll(studio, resp.json()["run_id"])
    assert loops.list_rodadas(studio.org_id, rec.id) == []
