"""Julia v2 A-EVAL: the publish path requires the mechanism suite (CONTRACT 3.5 E4) -- no override, LIVE driver
only, current hash; the judge suite is advisory unless the agent opts in to blocking."""
from __future__ import annotations

from uuid import UUID, uuid4

from app.studio.eval_mecanismo import MecanismoGateRun, MecanismoRequisito
from app.studio.models import GateRun

BASE = "/api/studio/agents"
SECTIONS = {"secoes": [
    {"chave": "identidade", "titulo": "Identidade", "ordem": 10, "conteudo": "Você é estrategista.", "ativo": True},
    {"chave": "regras", "titulo": "Regras", "ordem": 20, "conteudo": "Seja direta.", "ativo": True},
]}


def _draft(studio, key="isa"):
    assert studio.post(BASE, json={"key": key, "nome": "Isa"}).status_code == 201
    draft = studio.put(f"{BASE}/{key}/draft/sections", json=SECTIONS).json()
    return draft


def _agent_id(studio, key="isa") -> UUID:
    return UUID(studio.get(f"{BASE}/{key}").json()["id"])


def _req(studio, draft, *, hash_=None, **overrides) -> MecanismoRequisito:
    run = overrides.pop("run", MecanismoGateRun(
        id=uuid4(), compiled_hash=hash_ or draft["compiled_hash"], status="concluida", driver="live",
        completa=True, aprovado=True, orcamento_excedido=False, total_casos=4, casos_aprovados=4,
    ))
    req = MecanismoRequisito(exigido=True, casos_ativos=4, run=run, **overrides)
    studio.gate.set_mecanismo(studio.org_id, UUID(draft["id"]), req)
    return req


def _pass_judge(studio, draft):
    run = GateRun(id=uuid4(), score=0.9, limiar=0.8, compiled_hash=draft["compiled_hash"], status="concluida", completa=True, total=3)
    studio.gate.set_run(studio.org_id, UUID(draft["id"]), run)
    studio.store.register_eval_run(
        studio.org_id, UUID(draft["id"]), run_id=run.id, score=0.9, compiled_hash=draft["compiled_hash"], completa=True, total=3,
    )
    return run


def test_an_agent_without_the_mechanism_requirement_publishes_as_before(studio):
    draft = _draft(studio)
    _pass_judge(studio, draft)
    assert studio.post(f"{BASE}/isa/draft/publish", json={}).status_code == 200


def test_publish_is_refused_when_the_mechanism_suite_never_ran(studio):
    draft = _draft(studio)
    _pass_judge(studio, draft)
    studio.gate.set_mecanismo(studio.org_id, UUID(draft["id"]), MecanismoRequisito(exigido=True, casos_ativos=4, run=None))
    resp = studio.post(f"{BASE}/isa/draft/publish", json={})
    assert resp.status_code == 409
    assert resp.json()["code"] == "mecanismo_reprovado" and resp.json()["motivo"] == "sem_execucao"


def test_no_override_can_stand_in_for_the_mechanism_suite(studio):
    draft = _draft(studio)
    studio.gate.set_mecanismo(studio.org_id, UUID(draft["id"]), MecanismoRequisito(exigido=True, casos_ativos=4, run=None))
    resp = studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": "x" * 30})
    assert resp.status_code == 409 and resp.json()["code"] == "mecanismo_reprovado"
    assert studio.get(f"{BASE}/isa").json()["versao_ativa"] is None


def test_required_but_empty_suite_is_not_green(studio):
    draft = _draft(studio)
    studio.gate.set_mecanismo(studio.org_id, UUID(draft["id"]), MecanismoRequisito(exigido=True, casos_ativos=0))
    resp = studio.post(f"{BASE}/isa/draft/publish", json={})
    assert resp.status_code == 409 and resp.json()["motivo"] == "sem_casos"


def test_a_fake_driver_run_does_not_open_the_gate(studio):
    draft = _draft(studio)
    run = MecanismoGateRun(
        id=uuid4(), compiled_hash=draft["compiled_hash"], status="concluida", driver="fake", completa=True,
        aprovado=True, orcamento_excedido=False, total_casos=4, casos_aprovados=4,
    )
    _req(studio, draft, run=run)
    assert studio.post(f"{BASE}/isa/draft/publish", json={}).json()["motivo"] == "driver_nao_live"


def test_a_run_of_an_older_prompt_does_not_open_the_gate(studio):
    draft = _draft(studio)
    _req(studio, draft, hash_="sha256:antigo")
    assert studio.post(f"{BASE}/isa/draft/publish", json={}).json()["motivo"] == "hash_diferente"


def test_green_mechanism_publishes_even_with_no_judge_run_and_audits_it(studio):
    draft = _draft(studio)
    req = _req(studio, draft)
    resp = studio.post(f"{BASE}/isa/draft/publish", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ativa"
    assert str(req.run.id) in (body["publish_override_reason"] or "")  # the audit trail names the mechanism run


def test_green_mechanism_with_blocking_judge_still_needs_the_judge_run(studio):
    draft = _draft(studio)
    _req(studio, draft, comportamento_bloqueia=True)
    resp = studio.post(f"{BASE}/isa/draft/publish", json={})
    assert resp.status_code == 409 and resp.json()["code"] == "eval_required"
    _pass_judge(studio, draft)
    assert studio.post(f"{BASE}/isa/draft/publish", json={}).status_code == 200
