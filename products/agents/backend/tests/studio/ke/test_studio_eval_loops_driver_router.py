"""Migration 088 through the API: the loop's mode, its lifecycle events, live run progress, errored runs, and the preflight that
refuses BEFORE a run is booked."""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException

from app.routers.studio_evals_router import get_eval_scheduler_dep, get_preflight_dep
from app.stores.studio_eval_runs import FakeEvalRunWriter
from app.stores.studio_evals import EvalCaseInput
from tests.studio.ke.conftest import DEFAULT_ORG_ID, seed_draft, seed_org_role, seed_studio_agent

LOOPS = "/api/studio/agents/isaia/evals/loops"
RUNS = "/api/studio/agents/isaia/evals/runs"
MEC = "/api/studio/agents/isaia/mecanismo-runs"


def _seed(ke_client, *, n=2, **loop_kw):
    agent = seed_studio_agent(ke_client)
    version_id = seed_draft(ke_client, agent).id
    for i in range(n):
        ke_client.stores.evals.create_case(
            DEFAULT_ORG_ID, agent.id, EvalCaseInput(slug=f"c{i}", titulo=f"Caso {i}", entrada="e", criterios={"deve": ["x"], "nao_deve": []}))
    loop = ke_client.post(LOOPS, json={"suite": "comportamento", "rodadas_planejadas": 10, **loop_kw}).json()
    return agent, version_id, loop


def _post_run(ke_client, version_id, **extra):
    app = ke_client.raw().app
    app.dependency_overrides[get_eval_scheduler_dep] = lambda: (lambda run_id: None)
    try:
        return ke_client.post(RUNS, json={"version_id": str(version_id), **extra})
    finally:
        app.dependency_overrides.pop(get_eval_scheduler_dep, None)


def test_a_loop_opens_in_automatic_mode_by_default_and_says_what_it_is_doing(ke_client):
    seed_org_role(ke_client, role="owner")
    seed_studio_agent(ke_client)
    body = ke_client.post(LOOPS, json={"suite": "comportamento", "rodadas_planejadas": 5}).json()
    assert body["modo"] == "automatico" and body["estado_driver"] == "automatico" and body["aviso"] is None
    ev = ke_client.get(f"{LOOPS}/{body['id']}/eventos").json()["items"]
    assert [e["evento"] for e in ev] == ["loop_iniciado"] and ev[0]["detalhe"]["modo"] == "automatico"


def test_a_manual_loop_says_it_waits_for_the_owner(ke_client):
    seed_org_role(ke_client, role="owner")
    seed_studio_agent(ke_client)
    body = ke_client.post(LOOPS, json={"suite": "comportamento", "rodadas_planejadas": 5, "modo": "manual"}).json()
    assert body["modo"] == "manual" and body["estado_driver"] == "manual"


def test_the_mode_can_be_paused_and_resumed_each_change_is_an_event_and_a_stopped_loop_refuses(ke_client):
    seed_org_role(ke_client, role="owner")
    seed_studio_agent(ke_client)
    lid = ke_client.post(LOOPS, json={"suite": "comportamento", "rodadas_planejadas": 5}).json()["id"]
    assert ke_client.put(f"{LOOPS}/{lid}/modo", json={"modo": "manual"}).json()["modo"] == "manual"
    assert ke_client.put(f"{LOOPS}/{lid}/modo", json={"modo": "automatico"}).json()["modo"] == "automatico"
    assert ke_client.put(f"{LOOPS}/{lid}/modo", json={"modo": "outro"}).status_code == 422
    assert [e["evento"] for e in ke_client.get(f"{LOOPS}/{lid}/eventos").json()["items"]] == ["loop_iniciado", "modo_alterado", "modo_alterado"]
    ke_client.post(f"{LOOPS}/{lid}/stop", json={})
    gone = ke_client.put(f"{LOOPS}/{lid}/modo", json={"modo": "manual"})
    assert gone.status_code == 409 and gone.json()["code"] == "loop_ja_encerrado"
    assert ke_client.get(f"{LOOPS}/{uuid4()}/eventos").status_code == 404


def test_cancelling_the_run_of_an_automatic_loop_pauses_it(ke_client):
    seed_org_role(ke_client, role="owner")
    agent, version_id, loop = _seed(ke_client)
    assert loop["modo"] == "automatico"
    run = _post_run(ke_client, version_id, loop_id=loop["id"]).json()
    ke_client.post(f"{RUNS}/{run['id']}/cancel")
    s = ke_client.get(f"{LOOPS}/{loop['id']}").json()
    assert s["modo"] == "manual" and s["estado_driver"] == "manual"


def test_the_run_progress_endpoint_reports_the_servers_numbers_without_inventing_a_score(ke_client):
    seed_org_role(ke_client, role="owner")
    agent, version_id, loop = _seed(ke_client, n=4)
    run = _post_run(ke_client, version_id, loop_id=loop["id"]).json()
    p = ke_client.get(f"{RUNS}/{run['id']}/progresso").json()
    assert (p["status"], p["total"], p["concluidos"], p["ativo"], p["score_parcial"]) == ("pendente", 4, 0, True, None)
    w = FakeEvalRunWriter(ke_client.stores.evals)
    w.claim_run(DEFAULT_ORG_ID, UUID(run["id"]))
    res = ke_client.stores.evals.list_results_with_cases(DEFAULT_ORG_ID, agent.id, UUID(run["id"]))
    for r, st, sc in zip(res, ("aprovado", "reprovado", "erro"), (1.0, 0.5, None)):
        w.set_result(DEFAULT_ORG_ID, UUID(run["id"]), r.result.case_id, status=st, saida="s", score=sc, veredito=[], notas_juiz="n",
                     duracao_ms=1, custo_usd=0.25)
    p = ke_client.get(f"{RUNS}/{run['id']}/progresso").json()
    assert (p["concluidos"], p["aprovados"], p["reprovados"], p["erros"]) == (3, 1, 1, 1)
    assert p["score_parcial"] == 0.75 and p["custo_usd"] == 0.75  # the errored case is out of the denominator
    assert ke_client.get(f"{RUNS}/{uuid4()}/progresso").status_code == 404


def test_an_all_error_run_has_no_score_the_status_erro_and_stops_its_loop_with_the_reason(ke_client):
    seed_org_role(ke_client, role="owner")
    agent, version_id, loop = _seed(ke_client, n=2)
    run = _post_run(ke_client, version_id, loop_id=loop["id"]).json()
    w = FakeEvalRunWriter(ke_client.stores.evals)
    w.claim_run(DEFAULT_ORG_ID, UUID(run["id"]))
    for r in ke_client.stores.evals.list_results_with_cases(DEFAULT_ORG_ID, agent.id, UUID(run["id"])):
        w.set_result(DEFAULT_ORG_ID, UUID(run["id"]), r.result.case_id, status="erro", saida=None, score=None, veredito=None,
                     notas_juiz="O turno foi recusado (qualificacao_indisponivel)", duracao_ms=1)
    w.finish_run(DEFAULT_ORG_ID, UUID(run["id"]), status="erro", aprovados=0, score=None, erro="2 de 2 casos terminaram em erro.",
                 erro_codigo="qualificacao_indisponivel", casos_com_erro=2)
    from app.studio.eval_loop_service import resumo_comportamento

    ke_client.stores.loop_service.fechar_sem_falhar(
        DEFAULT_ORG_ID, lambda: resumo_comportamento(ke_client.stores.evals, DEFAULT_ORG_ID, agent.id, UUID(run["id"])),
        run_id=UUID(run["id"]), run_tipo="comportamento")
    p = ke_client.get(f"{RUNS}/{run['id']}/progresso").json()
    assert (p["status"], p["ativo"], p["score_parcial"], p["erros"], p["erro_codigo"]) == ("erro", False, None, 2, "qualificacao_indisponivel")
    listed = ke_client.get(RUNS).json()["items"][0]
    assert listed["status"] == "erro" and listed["score"] is None and listed["erro_codigo"] == "qualificacao_indisponivel"
    s = ke_client.get(f"{LOOPS}/{loop['id']}").json()
    assert s["motivo_parada"] == "erro" and s["serie"][0]["status"] == "erro" and s["serie"][0]["score"] is None
    assert s["detalhe_parada"]["codigo"] == "qualificacao_indisponivel"


def test_a_preflight_refusal_books_nothing_and_names_the_reason(ke_client):
    seed_org_role(ke_client, role="owner")
    agent, version_id, loop = _seed(ke_client)

    def preflight(agent_):
        raise HTTPException(409, detail={"detail": "O agente não pode ser avaliado agora: O agente não tem padrão de qualificação.",
                                         "code": "qualificacao_indisponivel", "preflight": True})

    app = ke_client.raw().app
    app.dependency_overrides[get_preflight_dep] = lambda: preflight
    try:
        resp = _post_run(ke_client, version_id, loop_id=loop["id"])
    finally:
        app.dependency_overrides.pop(get_preflight_dep, None)
    assert resp.status_code == 409 and resp.json()["code"] == "qualificacao_indisponivel"
    assert ke_client.get(RUNS).json()["items"] == [] and ke_client.get(f"{LOOPS}/{loop['id']}").json()["serie"] == []
    assert "preflight_recusado" in [e["evento"] for e in ke_client.get(f"{LOOPS}/{loop['id']}/eventos").json()["items"]]
