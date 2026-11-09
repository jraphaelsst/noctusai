"""Eval consolidation orchestration over the Fake store: selection (skip consolidated+unaffected, why), recording (state moves +
append-only transitions), the mechanism pass counting, the partial-run guard, and the historical backfill (dry-run first)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.stores.studio_eval_consolidacao import CasoMeta, FakeConsolidacaoStore
from app.stores.studio_eval_mecanismo import FakeMecanismoStore
from app.stores.studio_evals import EvalCaseInput, FakeEvalStore
from app.studio.consolidacao_service import confirmar_selecao, reconstruir, registrar_resultados, selecionar
from app.studio.eval_driver import Estado, FakeEvalTurnDriver, TurnOutcome
from app.studio.eval_mecanismo_service import TodosConsolidados, concluir_suite_mecanismo, iniciar_suite_mecanismo

ORG, AGENT, VERSION = uuid4(), uuid4(), uuid4()
P0 = {"secao:a": "1", "secao:b": "1", "modelo": "m", "config": "c", "estrutura": "e"}
T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _store(n=3, crit=None, deps=None):
    ev = FakeEvalStore()
    st = FakeConsolidacaoStore(ev)
    ids = []
    for i in range(n):
        c = ev.create_case(ORG, AGENT, EvalCaseInput(slug=f"c{i}", titulo="t", entrada="e", criterios={"deve": ["x"], "nao_deve": []}))
        ids.append(c.id)
        st.set_caso(ORG, AGENT, c.id, criticidade=(crit or {}).get(i), depende_de=(deps or {}).get(i, None), depende_de_origem="declarada")
    return st, ids


def _passar(st, ids, n, partes=P0, h="h0", run=None, suite="comportamento"):
    for _ in range(n):
        registrar_resultados(st, org_id=ORG, agent_id=AGENT, suite=suite, run_id=run or uuid4(),
                             run_tipo="comportamento", hash_atual=h, partes=partes, resultados=[(i, ["aprovado"]) for i in ids])


def test_default_selection_skips_only_consolidated_unaffected_and_says_why():
    st, ids = _store(deps={0: ["secao:a"], 1: ["secao:a"]})
    _passar(st, ids[:2], 5)  # c0, c1 consolidated; c2 untouched
    sel = selecionar(st, org_id=ORG, agent_id=AGENT, suite="comportamento", ativos=ids, partes=dict(P0), hash_atual="h0", rodar_tudo=False)
    assert sel.rodar == [ids[2]]
    assert {p["case_id"] for p in sel.pulados} == set(ids[:2]) and all(p["motivo"] == "consolidado_nao_afetado" for p in sel.pulados)


def test_a_change_to_a_dependency_revalidates_only_the_dependents():
    st, ids = _store(deps={0: ["secao:a"], 1: ["secao:b"], 2: ["secao:b"]})
    _passar(st, ids, 5)
    sel = selecionar(st, org_id=ORG, agent_id=AGENT, suite="comportamento", ativos=ids, partes={**P0, "secao:a": "2"}, hash_atual="h1", rodar_tudo=False)
    assert sel.rodar == [ids[0]]
    run = uuid4()
    confirmar_selecao(st, sel, org_id=ORG, agent_id=AGENT, suite="comportamento", run_id=run, run_tipo="comportamento", partes={**P0, "secao:a": "2"}, hash_atual="h1")
    assert st.get_estados(ORG, AGENT)[ids[0]].estado == "revalidar"
    assert {p["case_id"] for p in st.list_pulados(ORG, run, "comportamento")} == {ids[1], ids[2]}
    assert st.get_run_partes(ORG, run, "comportamento")["secao:a"] == "2"
    mov = [t for t in st.transicoes if t["motivo"] == "afetado"]
    assert len(mov) == 1 and mov[0]["origem"] == "selecao" and mov[0]["partes_afetadas"] == ["secao:a"]


def test_rodar_tudo_runs_everything_and_skips_nothing():
    st, ids = _store(deps={0: ["secao:a"]})
    _passar(st, ids, 5)
    sel = selecionar(st, org_id=ORG, agent_id=AGENT, suite="comportamento", ativos=ids, partes=dict(P0), hash_atual="h0", rodar_tudo=True)
    assert sel.rodar == ids and not sel.pulados


def test_without_per_part_hashes_nothing_is_skipped_fail_safe():
    st, ids = _store(deps={0: ["secao:a"]})
    _passar(st, ids, 5)
    sel = selecionar(st, org_id=ORG, agent_id=AGENT, suite="comportamento", ativos=ids, partes=None, hash_atual="h-novo", rodar_tudo=False)
    assert sel.rodar == ids


def test_critical_needs_ten_and_transitions_are_recorded_with_run_and_hashes():
    st, ids = _store(n=1, crit={0: "critico"}, deps={0: ["secao:a"]})
    _passar(st, ids, 9)
    assert st.get_estados(ORG, AGENT)[ids[0]].estado == "em_validacao"
    _passar(st, ids, 1)
    assert st.get_estados(ORG, AGENT)[ids[0]].estado == "consolidado"
    last = st.transicoes[-1]
    assert (last["motivo"], last["criticidade"], last["sequencia_depois"], last["partes"]) == ("consolidado", "critico", 10, P0)


def test_error_result_is_neutral():
    st, ids = _store(n=1)
    _passar(st, ids, 3)
    registrar_resultados(st, org_id=ORG, agent_id=AGENT, suite="comportamento", run_id=uuid4(), run_tipo="comportamento",
                         hash_atual="h0", partes=P0, resultados=[(ids[0], ["erro", "pulado"])])
    assert st.get_estados(ORG, AGENT)[ids[0]].sequencia == 3


# ── mechanism ────────────────────────────────────────────────────────────────────────────────────────────


def _mec_store():
    ev = FakeEvalStore()
    ms = FakeMecanismoStore(ev)
    cs = FakeConsolidacaoStore(ev)
    roteiro = {"turnos": [{"lead": "quero comprar"}], "catalogo": [{"codigo": "AP-SINT-1"}]}
    for i in range(2):
        ev.create_case(ORG, AGENT, EvalCaseInput(slug=f"m{i}", titulo="m", entrada="e", criterios={}, suite="mecanismo", k=3,
                                                 roteiro=roteiro, asserts={"sem_violacoes": True}))
    for c in ev.list_cases(ORG, AGENT):
        cs.set_caso(ORG, AGENT, c.id, depende_de=["secao:a"], depende_de_origem="declarada")
    return ms, cs


def _ok_turn():
    return TurnOutcome(bolhas=("Qual o prazo?",), estado=Estado(estagio="novo"))


class _Driver(FakeEvalTurnDriver):
    tipo = "live"

    def __init__(self):
        super().__init__([_ok_turn()])


def _run_mec(ms, cs, partes, rodar_tudo=False):
    drv = _Driver()
    run_id, casos = iniciar_suite_mecanismo(ms, drv, org_id=ORG, agent_id=AGENT, version_id=VERSION, compiled_hash="h0",
                                            started_by=uuid4(), limite_usd=None, consolidacao=cs, partes=partes, rodar_tudo=rodar_tudo)
    total = len(ms.list_active_cases(ORG, AGENT))
    asyncio.run(concluir_suite_mecanismo(ms, drv, casos, org_id=ORG, run_id=run_id, limite_usd=None, consolidacao=cs,
                                         agent_id=AGENT, compiled_hash="h0", parcial=len(casos) < total))
    return run_id, casos


def test_mechanism_each_passing_execution_counts_as_one_pass_and_k3_run_adds_three():
    ms, cs = _mec_store()
    _run_mec(ms, cs, dict(P0))
    est = cs.get_estados(ORG, AGENT)
    assert [e.sequencia for e in est.values()] == [3, 3] and all(e.estado == "em_validacao" for e in est.values())
    _run_mec(ms, cs, dict(P0))  # 6 >= 5: consolidated mid-run, keeps counting
    assert all(e.estado == "consolidado" for e in cs.get_estados(ORG, AGENT).values())


def test_mechanism_default_run_skips_consolidated_and_a_partial_run_never_opens_the_gate():
    ms, cs = _mec_store()
    _run_mec(ms, cs, dict(P0)); _run_mec(ms, cs, dict(P0))
    ids = [c.id for c in ms.list_active_cases(ORG, AGENT)]
    with pytest.raises(TodosConsolidados):
        _run_mec(ms, cs, dict(P0))
    # one case is affected -> only it runs; the run is PARTIAL (completa/aprovado False) so the publish gate is untouched
    cs.set_caso(ORG, AGENT, ids[1], depende_de=["secao:b"], depende_de_origem="declarada")
    run_id, casos = _run_mec(ms, cs, {**P0, "secao:a": "2"})
    assert [c.id for c in casos] == [ids[0]]
    row = ms.runs[run_id]
    assert row["completa"] is False and row["aprovado"] is False
    assert {p["case_id"] for p in cs.list_pulados(ORG, run_id, "mecanismo")} == {ids[1]}


def test_mechanism_rodar_tudo_runs_everything_and_can_be_complete():
    ms, cs = _mec_store()
    _run_mec(ms, cs, dict(P0)); _run_mec(ms, cs, dict(P0))
    run_id, casos = _run_mec(ms, cs, dict(P0), rodar_tudo=True)
    assert len(casos) == 2 and ms.runs[run_id]["completa"] is True


def test_fake_driver_runs_are_not_evidence():
    ms, cs = _mec_store()
    drv = FakeEvalTurnDriver([_ok_turn()])
    run_id, casos = iniciar_suite_mecanismo(ms, drv, org_id=ORG, agent_id=AGENT, version_id=VERSION, compiled_hash="h0",
                                            started_by=uuid4(), limite_usd=None, consolidacao=cs, partes=dict(P0))
    asyncio.run(concluir_suite_mecanismo(ms, drv, casos, org_id=ORG, run_id=run_id, limite_usd=None, consolidacao=cs,
                                         agent_id=AGENT, compiled_hash="h0"))
    assert cs.get_estados(ORG, AGENT) == {}


# ── backfill ─────────────────────────────────────────────────────────────────────────────────────────────


def _hist(st, ids, hashes_partes):
    for i, (h, partes) in enumerate(hashes_partes):
        st.hist_comportamento.append({
            "run_id": uuid4(), "ts": T0 + timedelta(hours=i), "compiled_hash": h, "version_id": VERSION, "partes": partes,
            "resultados": {c: "aprovado" for c in ids}})


def test_backfill_dry_run_writes_nothing_and_reports_counts():
    st, ids = _store(deps={0: ["secao:a"], 1: ["secao:a"], 2: None})
    _hist(st, ids, [("h0", dict(P0))] * 5)
    rel = reconstruir(st, org_id=ORG, agent_id=AGENT, aplicar=False)
    assert rel.estados == {"consolidado": 3} and rel.transicoes > 0 and rel.aplicado is False
    assert st.get_estados(ORG, AGENT) == {} and st.transicoes == []


def test_backfill_apply_is_idempotent_and_tags_transitions_as_backfill():
    st, ids = _store()
    _hist(st, ids, [("h0", dict(P0))] * 5)
    reconstruir(st, org_id=ORG, agent_id=AGENT, aplicar=True)
    n = len(st.transicoes)
    assert n and all(t["origem"] == "backfill" for t in st.transicoes)
    again = reconstruir(st, org_id=ORG, agent_id=AGENT, aplicar=True)
    assert len(st.transicoes) == n and again.casos_ja_rastreados == 3


def test_backfill_hash_change_without_parts_follows_the_owner_policy_and_the_conservative_one():
    st, ids = _store(deps={0: ["secao:a"], 1: None, 2: ["secao:a"]})
    _hist(st, ids, [("h0", None)] * 5 + [("h1", None)] + [("h1", None)] * 2)  # 5 passes, then a hash change, then 3 passes
    dono = reconstruir(st, org_id=ORG, agent_id=AGENT, politica_sem_partes="dono")
    # declared deps + unknown parts: assumed unaffected (stays consolidated); NO deps: affected -> revalidated -> back after 3
    assert dono.casos_por_estado["consolidado"] and dono.estados["consolidado"] == 3
    cons = reconstruir(st, org_id=ORG, agent_id=AGENT, politica_sem_partes="conservadora")
    assert cons.estados["consolidado"] == 3  # 3 passes after the change also reconsolidate everyone (revalidation = 3)


def test_backfill_recomputes_parts_only_when_the_recompiled_hash_matches():
    st, ids = _store(deps={0: ["secao:a"], 1: ["secao:a"], 2: ["secao:a"]})
    _hist(st, ids, [("h0", None)] * 5 + [("h1", None)] * 3)
    por_hash = {"h0": dict(P0), "h1": {**P0, "secao:b": "2"}}  # h1 only changed secao:b: not a dependency
    rel = reconstruir(st, org_id=ORG, agent_id=AGENT,
                      recomputar_partes=lambda v, h: por_hash[h] if h == "h0" else None)  # h1 not recoverable
    assert (rel.runs_com_partes, rel.runs_sem_partes) == (5, 3)
    assert rel.estados == {"consolidado": 3}  # unknown parts + declared deps: assumed unaffected (owner policy), reported above
    st2, ids2 = _store(deps={0: ["secao:a"], 1: ["secao:a"], 2: ["secao:a"]})
    _hist(st2, ids2, [("h0", None)] * 5 + [("h1", None)] * 2)
    rel2 = reconstruir(st2, org_id=ORG, agent_id=AGENT, recomputar_partes=lambda v, h: por_hash[h])
    assert rel2.runs_com_partes == 7 and rel2.estados == {"consolidado": 3}


def test_backfill_proposes_criticality_and_dependency_gaps():
    ev = FakeEvalStore()
    st = FakeConsolidacaoStore(ev)
    a = ev.create_case(ORG, AGENT, EvalCaseInput(slug="adv", titulo="t", entrada="e", criterios={"deve": ["x"], "nao_deve": []}, tags=("adversarial", "skill:qualificar")))
    ev.create_case(ORG, AGENT, EvalCaseInput(slug="tom", titulo="t", entrada="e", criterios={"deve": ["x"], "nao_deve": []}, tags=("tom",)))
    rel = reconstruir(st, org_id=ORG, agent_id=AGENT, partes_conhecidas=["skill:qualificar"], usar_deps_propostas=True, aplicar=True)
    assert rel.criticidade_proposta == {"normal": 1, "critico": 1} and rel.deps_inferidas == 1
    assert rel.deps_sem_inferencia == ["comportamento:tom"]
    m = st.list_meta(ORG, AGENT)[a.id]
    assert (m.criticidade, m.criticidade_origem, m.depende_de, m.depende_de_origem) == ("critico", "sugerida", ("skill:qualificar",), "inferida")
