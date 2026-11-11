"""A ``comportamento`` (judge) case may carry the WORLD its ``contexto`` narrates (``roteiro``: estado_inicial / catalogo /
fixture, no turnos). Without it the engine's state block says the lead is brand new while the contexto says an imóvel was
already shown, and the case grades that contradiction (behaviour suite 0.979 -> 0.778, 2026-11-08)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.studio.eval_mecanismo import RoteiroInvalido, validar_mundo_juiz

MUNDO = {
    "catalogo": [{"codigo": "ONE8970", "titulo": "Casa 3 quartos", "preco": 1050000}],
    "estado_inicial": {"criterios": {"operacao": "compra"}, "lotes": [["ONE8970"]]},
    "fixture": {"modo": "ligado"},
}
EVALS = Path(__file__).resolve().parents[4] / "projects" / "julia-v2" / "content-v3" / "evals"


def test_a_world_without_turns_is_valid():
    validar_mundo_juiz(MUNDO)


@pytest.mark.parametrize("ruim", [
    {**MUNDO, "turnos": [{"lead": "oi"}]},          # a judge case is ONE turn
    {**MUNDO, "canarios": ["abcdef"]},
    {"estado_inicial": {"campo_novo": 1}},          # unknown estado field
    {"catalogo": "x"},
])
def test_anything_else_is_refused(ruim):
    with pytest.raises(RoteiroInvalido):
        validar_mundo_juiz(ruim)


def test_a_world_with_personal_data_is_refused():
    from app.studio.eval_pii import EvalFixtureComPii

    with pytest.raises(EvalFixtureComPii):
        validar_mundo_juiz({"fixture": {"x": "529.982.247-25"}})


def test_the_store_accepts_a_world_on_a_judge_case_and_still_refuses_k_and_asserts():
    from app.stores.studio_evals import _validate_caso

    crit = {"deve": ["a"], "nao_deve": []}
    _validate_caso(suite="comportamento", criterios=crit, k=3, roteiro=MUNDO, asserts=None, titulo="t", entrada="e", contexto="c")
    with pytest.raises(ValueError):
        _validate_caso(suite="comportamento", criterios=crit, k=3, roteiro=MUNDO, asserts={"x": 1}, titulo="t", entrada="e", contexto="c")


def test_the_repo_mirror_worlds_are_all_valid():
    mundos = [json.loads(f.read_text()) for f in EVALS.glob("*.json")]
    com_mundo = [d for d in mundos if isinstance(d, dict) and d.get("roteiro")]
    assert com_mundo
    for d in com_mundo:
        validar_mundo_juiz(d["roteiro"], titulo=d["titulo"], entrada=d["entrada"], contexto=d.get("contexto"))


def test_a_judge_case_can_be_created_and_patched_with_a_world_but_not_with_k_or_asserts():
    from uuid import uuid4

    from app.stores.studio_evals import EvalCaseInput, FakeEvalStore

    store, org, agent = FakeEvalStore(), uuid4(), uuid4()
    caso = store.create_case(org, agent, EvalCaseInput(
        slug="j1", titulo="t", entrada="e", criterios={"deve": ["a"], "nao_deve": []}, contexto="c"))
    assert caso.roteiro is None
    novo = store.update_case(org, agent, caso.id, roteiro=MUNDO)
    assert novo.roteiro == MUNDO and novo.suite == "comportamento"
    with pytest.raises(ValueError):
        store.update_case(org, agent, caso.id, k=5)
    with pytest.raises(RoteiroInvalido):
        store.update_case(org, agent, caso.id, roteiro={**MUNDO, "turnos": [{"lead": "oi"}]})
