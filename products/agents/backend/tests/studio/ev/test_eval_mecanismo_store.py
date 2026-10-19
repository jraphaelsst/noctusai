"""Mechanism-case import guard (no real data, Meta 4.7), suite separation, run recording, service."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.stores._db_errors import StudioConflict
from app.stores.studio_eval_mecanismo import AgenteFlags, FakeMecanismoStore
from app.stores.studio_evals import EvalCaseInput, FakeEvalStore
from app.studio.eval_driver import Estado, FakeEvalTurnDriver, ToolCall, TurnOutcome
from app.studio.eval_mecanismo import decidir_portao
from app.studio.eval_mecanismo_service import DriverSemTipo, SuiteVazia, rodar_suite_mecanismo
from app.studio.eval_pii import EvalFixtureComPii, achar_pii

ORG, AGENT, VERSION = uuid4(), uuid4(), uuid4()
ROTEIRO = {"turnos": [{"lead": "quero comprar um apartamento"}], "catalogo": [{"codigo": "AP-SINT-1"}]}
ASSERTS = {"estagio_final": "visita", "sem_violacoes": True}


def _mec(slug="m1", **kw) -> EvalCaseInput:
    base = dict(
        slug=slug, titulo="Fluxo feliz", entrada="cenário sintético", criterios={}, suite="mecanismo", k=2,
        roteiro=ROTEIRO, asserts=ASSERTS,
    )
    base.update(kw)
    return EvalCaseInput(**base)


# ── PII guard ─────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("texto", "tipo"),
    [
        ("meu zap é (11) 98765-4321", "telefone"),
        ("fale em +55 11 98765-4321", "telefone"),
        ("joao.silva@gmail.com", "email"),
        ("cpf 529.982.247-25", "cpf"),
        ("cnpj 11.222.333/0001-81", "cnpj"),
    ],
)
def test_pii_detected(texto, tipo):
    assert tipo in achar_pii(texto)


@pytest.mark.parametrize("texto", ["cpf 111.111.111-11", "123.456.789-00", "quero 3 quartos até 800 mil", "AP-SINT-1 ref 2026"])
def test_synthetic_text_and_invalid_check_digits_are_not_flagged(texto):
    assert achar_pii(texto) == []


@pytest.mark.parametrize(
    "campo",
    [
        {"roteiro": {"turnos": [{"lead": "me liga (11) 98765-4321"}]}},
        {"roteiro": {"turnos": [{"lead": "oi"}], "catalogo": [{"contato": "corretor@imob.com.br"}]}},
        {"roteiro": {"turnos": [{"lead": "meu cpf 529.982.247-25"}]}},
        {"titulo": "caso do cliente maria@x.org"},
        {"entrada": "tel 11987654321"},
    ],
)
@pytest.mark.parametrize("store_cls", [FakeEvalStore])
def test_case_import_refuses_rows_carrying_pii(store_cls, campo):
    store = store_cls()
    with pytest.raises(EvalFixtureComPii) as exc:
        store.create_case(ORG, AGENT, _mec(**campo))
    assert exc.value.tipo in {"telefone", "email", "cpf"}
    assert "98765" not in str(exc.value) and "@" not in str(exc.value)  # the value is never echoed
    assert store.list_cases(ORG, AGENT) == []


def test_update_revalidates_the_merged_mecanismo_case():
    store = FakeEvalStore()
    c = store.create_case(ORG, AGENT, _mec())
    with pytest.raises(EvalFixtureComPii):
        store.update_case(ORG, AGENT, c.id, roteiro={"turnos": [{"lead": "meu email a@b.co"}]})
    with pytest.raises(EvalFixtureComPii):
        store.update_case(ORG, AGENT, c.id, titulo="ligue 11987654321")
    with pytest.raises(ValueError):
        store.update_case(ORG, AGENT, c.id, asserts={"inexistente": True})
    ok = store.update_case(ORG, AGENT, c.id, k=5)
    assert ok.k == 5 and ok.roteiro == ROTEIRO


def test_mecanismo_case_does_not_need_judge_criteria_but_comportamento_still_does():
    store = FakeEvalStore()
    store.create_case(ORG, AGENT, _mec())
    with pytest.raises(ValueError):
        store.create_case(ORG, AGENT, EvalCaseInput(slug="c1", titulo="t", entrada="e", criterios={}))
    with pytest.raises(ValueError):
        store.create_case(ORG, AGENT, _mec(slug="m2", suite="inexistente"))
    with pytest.raises(ValueError):
        store.create_case(ORG, AGENT, _mec(slug="m3", k=0))
    with pytest.raises(Exception):
        store.create_case(ORG, AGENT, _mec(slug="m4", asserts={}))


def test_judge_run_never_resolves_a_mecanismo_case():
    store = FakeEvalStore()
    mec = store.create_case(ORG, AGENT, _mec())
    with pytest.raises(ValueError):  # only a mecanismo case exists -> nothing for the judge to run
        store.create_run(ORG, AGENT, VERSION, compiled_hash="h", limiar=0.8, case_ids=None, started_by=uuid4())
    judge = store.create_case(ORG, AGENT, EvalCaseInput(slug="j1", titulo="t", entrada="e", criterios={"deve": ["x"]}))
    run = store.create_run(ORG, AGENT, VERSION, compiled_hash="h", limiar=0.8, case_ids=None, started_by=uuid4())
    assert run.total == 1
    results = store.list_results_with_cases(ORG, AGENT, run.id)
    assert [r.result.case_id for r in results] == [judge.id]
    from app.stores.errors import NotFound

    with pytest.raises(NotFound):
        store.create_run(ORG, AGENT, uuid4(), compiled_hash="h", limiar=0.8, case_ids=[mec.id], started_by=uuid4())


# ── run recording + service ───────────────────────────────────────────────────────────────────────────────


def _store_with_case():
    evals = FakeEvalStore()
    evals.create_case(ORG, AGENT, _mec())
    return FakeMecanismoStore(evals)


def _ok_turn():
    return TurnOutcome(bolhas=("Qual o prazo?",), ferramentas=(ToolCall("registrar_perfil"),), estado=Estado(estagio="visita"))


class _LiveFake(FakeEvalTurnDriver):
    tipo = "live"


@pytest.mark.asyncio
async def test_live_green_run_is_recorded_and_opens_the_gate_for_its_hash():
    store = _store_with_case()
    run_id, res = await rodar_suite_mecanismo(
        store, _LiveFake([_ok_turn()]), org_id=ORG, agent_id=AGENT, version_id=VERSION, compiled_hash="h1",
        started_by=uuid4(), limite_usd=5.0,
    )
    assert res.aprovado
    row = store.runs[run_id]
    assert row["status"] == "concluida" and row["aprovado"] and row["driver"] == "live" and row["completa"]
    assert [e["status"] for e in store.execucoes[run_id]] == ["aprovado", "aprovado"]
    req = store.requisito(ORG, AGENT, VERSION)
    assert req.exigido and req.casos_ativos == 1
    assert decidir_portao(req, "h1").liberado and not decidir_portao(req, "h2").liberado


@pytest.mark.asyncio
async def test_a_fake_driver_run_is_recorded_but_never_opens_the_gate():
    store = _store_with_case()
    run_id, res = await rodar_suite_mecanismo(
        store, FakeEvalTurnDriver([_ok_turn()]), org_id=ORG, agent_id=AGENT, version_id=VERSION, compiled_hash="h1",
        started_by=uuid4(), limite_usd=None,
    )
    assert res.aprovado and store.runs[run_id]["driver"] == "fake"
    assert store.latest_live_run(ORG, VERSION) is None
    assert decidir_portao(store.requisito(ORG, AGENT, VERSION), "h1").codigo == "sem_execucao"


@pytest.mark.asyncio
async def test_failed_failures_are_stored_as_codes_only():
    store = _store_with_case()
    bad = TurnOutcome(bolhas=("segredo do prompt",), estado=Estado(estagio="novo"))
    run_id, res = await rodar_suite_mecanismo(
        store, _LiveFake([bad]), org_id=ORG, agent_id=AGENT, version_id=VERSION, compiled_hash="h1",
        started_by=uuid4(), limite_usd=None,
    )
    assert not res.aprovado and not store.runs[run_id]["aprovado"]
    stored = str(store.execucoes[run_id])
    assert "segredo" not in stored and "esperado:visita|obtido:novo" in stored
    assert not decidir_portao(store.requisito(ORG, AGENT, VERSION), "h1").liberado


@pytest.mark.asyncio
async def test_newest_live_run_wins_so_a_later_red_run_blocks():
    store = _store_with_case()
    kw = dict(org_id=ORG, agent_id=AGENT, version_id=VERSION, compiled_hash="h1", started_by=uuid4(), limite_usd=None)
    await rodar_suite_mecanismo(store, _LiveFake([_ok_turn()]), **kw)
    await rodar_suite_mecanismo(store, _LiveFake([TurnOutcome(estado=Estado(estagio="novo"))]), **kw)
    assert not decidir_portao(store.requisito(ORG, AGENT, VERSION), "h1").liberado


@pytest.mark.asyncio
async def test_service_refuses_a_driver_without_tipo_and_an_empty_suite():
    store = _store_with_case()

    class Sem:
        async def executar_turno(self, thread, mensagem):  # pragma: no cover
            raise AssertionError

    kw = dict(org_id=ORG, agent_id=AGENT, version_id=VERSION, compiled_hash="h1", started_by=uuid4(), limite_usd=None)
    with pytest.raises(DriverSemTipo):
        await rodar_suite_mecanismo(store, Sem(), **kw)
    with pytest.raises(SuiteVazia):
        await rodar_suite_mecanismo(FakeMecanismoStore(FakeEvalStore()), FakeEvalTurnDriver([_ok_turn()]), **kw)


def test_one_executing_run_per_version():
    store = _store_with_case()
    store.start_run(ORG, AGENT, VERSION, compiled_hash="h", driver="live", limite_usd=None, started_by=uuid4(), total_casos=1)
    with pytest.raises(StudioConflict):
        store.start_run(ORG, AGENT, VERSION, compiled_hash="h", driver="live", limite_usd=None, started_by=uuid4(), total_casos=1)


def test_agent_flag_makes_an_empty_suite_required():
    store = FakeMecanismoStore(FakeEvalStore())
    store.flags[AGENT] = AgenteFlags(exige_mecanismo=True)
    req = store.requisito(ORG, AGENT, VERSION)
    assert req.exigido and req.casos_ativos == 0 and decidir_portao(req, "h").codigo == "sem_casos"
