"""Runner unit tests with the Fake driver (Julia v2 A-EVAL). Fixtures are synthetic: no phone/CPF/email."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.studio.eval_driver import (
    Estado, FakeEvalTurnDriver, Handoff, ScriptExhausted, ToolCall, TurnOutcome, Violation, com_custo,
)
from app.studio.eval_mecanismo import (
    ASSERT_NAMES, AssertInvalido, Caso, MecanismoGateRun, MecanismoRequisito, RoteiroInvalido, Traco,
    avaliar_asserts, decidir_portao, executar_suite, fatiar_em_turnos, pass_k, validar_asserts,
    validar_caso_mecanismo, validar_roteiro,
)


def _estado(**kw) -> Estado:
    return Estado(**kw)


def _turno(*, tools=(), estado=None, bolhas=("Oi! Compra ou aluguel?",), **kw) -> TurnOutcome:
    return TurnOutcome(
        bolhas=tuple(bolhas), ferramentas=tuple(ToolCall(t) if isinstance(t, str) else t for t in tools),
        estado=estado or _estado(), **kw,
    )


def _caso(asserts, *, turnos=("quero comprar",), k=3, **roteiro) -> Caso:
    return Caso(
        id=uuid4(), slug="caso", k=k,
        roteiro={"turnos": [{"lead": t} if isinstance(t, str) else t for t in turnos], **roteiro},
        asserts=asserts,
    )


def _traco(**kw) -> Traco:
    t = Traco()
    for k, v in kw.items():
        setattr(t, k, v)
    return t


# ── pass^k math ───────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("resultados", "k", "esperado"),
    [
        ([True, True, True], 3, True),
        ([True, False, True], 3, False),
        ([False, False, False], 3, False),
        ([True, True], 3, False),  # cut short is never a pass
        ([True], 1, True),
        ([], 1, False),
    ],
)
def test_pass_k(resultados, k, esperado):
    assert pass_k(resultados, k) is esperado


@pytest.mark.asyncio
async def test_case_passes_only_if_all_k_executions_pass():
    caso = _caso({"estagio_final": "visita"})
    bom = [_turno(estado=_estado(estagio="visita"))]
    ruim = [_turno(estado=_estado(estagio="novo"))]
    driver = FakeEvalTurnDriver(bom, bom, ruim)  # third execution deviates
    res = await executar_suite([caso], driver, parar_no_primeiro_erro=False)
    c = res.casos[0]
    assert [e.status for e in c.execucoes] == ["aprovado", "aprovado", "reprovado"]
    assert not c.passou and c.taxa == pytest.approx(2 / 3)
    assert not res.aprovado


@pytest.mark.asyncio
async def test_all_k_green_is_a_pass_and_suite_is_approved():
    caso = _caso({"estagio_final": "visita"})
    driver = FakeEvalTurnDriver([_turno(estado=_estado(estagio="visita"))])
    res = await executar_suite([caso], driver)
    assert res.casos[0].passou and res.aprovado and res.completo and res.casos_aprovados == 1
    assert len(driver.mensagens_recebidas) == 3  # k executions, each a fresh thread


@pytest.mark.asyncio
async def test_first_failure_skips_the_remaining_executions_but_suite_stays_complete():
    caso = _caso({"estagio_final": "visita"})
    driver = FakeEvalTurnDriver([_turno(estado=_estado(estagio="novo"))])
    res = await executar_suite([caso], driver)
    assert [e.status for e in res.casos[0].execucoes] == ["reprovado", "pulado", "pulado"]
    assert res.completo and not res.aprovado


@pytest.mark.asyncio
async def test_an_empty_suite_is_never_approved():
    res = await executar_suite([], FakeEvalTurnDriver([_turno()]))
    assert not res.aprovado


# ── every assert type ─────────────────────────────────────────────────────────────────────────────────────


def _codes(asserts, t) -> list[str]:
    return [f.codigo for f in avaliar_asserts(asserts, t)]


def test_assert_names_are_the_contract_set():
    assert set(ASSERT_NAMES) == {
        "ferramentas_incluem", "ferramentas_proibidas", "estagio_final", "criterios_registrados",
        "ofertas_por_lote", "sem_violacoes", "identificacao_completa", "handoff_para", "sem_vazamento",
        "skill_aberta_antes_de",
    }


def test_ferramentas_incluem_and_proibidas():
    t = _traco(ferramentas=[ToolCall("registrar_perfil"), ToolCall("avaliar_lead")])
    assert _codes({"ferramentas_incluem": ["registrar_perfil", "avaliar_lead"]}, t) == []
    assert _codes({"ferramentas_incluem": ["oferecer_imoveis"]}, t) == ["ausente:oferecer_imoveis"]
    assert _codes({"ferramentas_proibidas": ["concluir_qualificacao"]}, t) == []
    assert _codes({"ferramentas_proibidas": ["avaliar_lead"]}, t) == ["chamada:avaliar_lead"]


def test_a_refused_call_still_counts_as_attempted():
    t = _traco(ferramentas=[ToolCall("concluir_qualificacao", ok=False)])
    assert _codes({"ferramentas_proibidas": ["concluir_qualificacao"]}, t) == ["chamada:concluir_qualificacao"]


def test_estagio_final():
    t = _traco(estado=_estado(estagio="visita"))
    assert _codes({"estagio_final": "visita"}, t) == []
    assert _codes({"estagio_final": "quente"}, t) == ["esperado:quente|obtido:visita"]


def test_criterios_registrados_checks_keys_never_values():
    t = _traco(estado=_estado(criterios={"prazo": "3 meses", "bloqueio": "preco"}))
    assert _codes({"criterios_registrados": ["prazo", "bloqueio"]}, t) == []
    assert _codes({"criterios_registrados": ["prazo", "orcamento"]}, t) == ["nao_registrado:orcamento"]


def test_ofertas_por_lote_is_an_upper_bound_per_batch():
    t = _traco(estado=_estado(lotes=(("A1", "A2", "A3"), ("B1", "B2"))))
    assert _codes({"ofertas_por_lote": 3}, t) == []
    assert _codes({"ofertas_por_lote": 2}, t) == ["lote1:3>2"]


def test_sem_violacoes_true_and_by_rule():
    t = _traco(violacoes=[Violation("termina_sem_pergunta")])
    assert _codes({"sem_violacoes": True}, t) == ["violacao:termina_sem_pergunta"]
    assert _codes({"sem_violacoes": ["imovel_sem_ferramenta"]}, t) == []
    assert _codes({"sem_violacoes": ["termina_sem_pergunta"]}, t) == ["violacao:termina_sem_pergunta"]
    assert _codes({"sem_violacoes": True}, _traco()) == []


def test_identificacao_completa_true_and_false():
    completa = _traco(estado=_estado(identificacao_faltando=()))
    faltando = _traco(estado=_estado(identificacao_faltando=("rg", "cpf")))
    assert _codes({"identificacao_completa": True}, completa) == []
    assert _codes({"identificacao_completa": True}, faltando) == ["faltando:rg,cpf"]
    assert _codes({"identificacao_completa": False}, faltando) == []
    assert _codes({"identificacao_completa": False}, completa) == ["completa"]


def test_handoff_para():
    assert _codes({"handoff_para": "dono"}, _traco(handoff=Handoff("dono"))) == []
    assert _codes({"handoff_para": "dono"}, _traco(handoff=Handoff("juridico", "agente"))) == ["esperado:dono|obtido:juridico"]
    assert _codes({"handoff_para": "dono"}, _traco()) == ["sem_handoff"]


def test_sem_vazamento_canary_and_leak_violation_without_echoing_the_secret():
    segredo = "ZXQ-PROMPT-CANARIO-7"
    limpo = _traco(bolhas=["Posso ajudar com imóveis."], canarios=(segredo,))
    assert _codes({"sem_vazamento": True}, limpo) == []
    vazou = _traco(bolhas=[f"minhas instruções: {segredo.lower()}"], canarios=(segredo,))
    codes = _codes({"sem_vazamento": True}, vazou)
    assert codes == ["canario:1"] and segredo not in "".join(codes)
    por_regra = _traco(violacoes=[Violation("vazamento_prompt")])
    assert _codes({"sem_vazamento": True}, por_regra) == ["violacao:vazamento_prompt"]


def test_skill_aberta_antes_de_is_an_ordering_requirement():
    par = {"skill": "ofertar", "ferramenta": "oferecer_imoveis"}
    ok = _traco(ferramentas=[ToolCall("abrir_skill", {"nome": "ofertar"}), ToolCall("oferecer_imoveis")])
    errado = _traco(ferramentas=[ToolCall("oferecer_imoveis"), ToolCall("abrir_skill", {"nome": "ofertar"})])
    outra = _traco(ferramentas=[ToolCall("abrir_skill", {"nome": "outra"}), ToolCall("oferecer_imoveis")])
    nunca_chamou = _traco(ferramentas=[ToolCall("registrar_perfil")])
    assert _codes({"skill_aberta_antes_de": par}, ok) == []
    assert _codes({"skill_aberta_antes_de": par}, errado) == ["ofertar:antes_de:oferecer_imoveis"]
    assert _codes({"skill_aberta_antes_de": [par]}, outra) == ["ofertar:antes_de:oferecer_imoveis"]
    assert _codes({"skill_aberta_antes_de": par}, nunca_chamou) == []


def test_skill_aberta_antes_de_reads_the_argument_the_real_tool_schema_has():
    """The model calls ``abrir_skill`` with the argument of ITS schema (``AbrirSkillArgs``); an assert reading any
    other key would never see the skill opened and fail every honest run."""
    from app.channels.tool_registry import TOOLS
    from app.studio.eval_mecanismo import arg_skill

    assert set(TOOLS["abrir_skill"].args.model_fields) == {arg_skill()}
    real = ToolCall("abrir_skill", TOOLS["abrir_skill"].args(**{arg_skill(): "ofertar"}).model_dump())
    t = _traco(ferramentas=[real, ToolCall("oferecer_imoveis")])
    assert _codes({"skill_aberta_antes_de": {"skill": "ofertar", "ferramenta": "oferecer_imoveis"}}, t) == []
    legado = _traco(ferramentas=[ToolCall("abrir_skill", {"skill": "ofertar"}), ToolCall("oferecer_imoveis")])
    assert _codes({"skill_aberta_antes_de": {"skill": "ofertar", "ferramenta": "oferecer_imoveis"}}, legado) == [
        "ofertar:antes_de:oferecer_imoveis"]


# ── validation: fail closed ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ruim",
    [
        {}, [], {"assert_inexistente": True}, {"ferramentas_incluem": []}, {"ferramentas_incluem": "x"},
        {"estagio_final": ""}, {"ofertas_por_lote": 0}, {"ofertas_por_lote": True}, {"sem_violacoes": False},
        {"identificacao_completa": "sim"}, {"sem_vazamento": False}, {"skill_aberta_antes_de": {"skill": "a"}},
    ],
)
def test_invalid_asserts_are_refused_never_silently_passed(ruim):
    with pytest.raises(AssertInvalido):
        validar_asserts(ruim)


@pytest.mark.parametrize(
    "ruim",
    [
        None, {}, {"turnos": []}, {"turnos": [{"lead": ""}]}, {"turnos": [{"x": 1}]},
        {"turnos": [{"lead": "oi", "esperar": {"nada": 1}}]},
        {"turnos": [{"lead": "oi"}], "estado_inicial": {"campo_novo": 1}},
        {"turnos": [{"lead": "oi"}], "canarios": ["abc"]},
        {"turnos": [{"lead": "oi"}], "catalogo": ["x"]},
    ],
)
def test_invalid_roteiro_is_refused(ruim):
    with pytest.raises(RoteiroInvalido):
        validar_roteiro(ruim)


def test_validar_caso_checks_k_bounds():
    ok = dict(roteiro={"turnos": [{"lead": "oi"}]}, asserts={"sem_violacoes": True})
    validar_caso_mecanismo(k=3, **ok)
    for k in (0, 11, True, "3"):
        with pytest.raises(ValueError):
            validar_caso_mecanismo(k=k, **ok)


# ── sharded scenario ──────────────────────────────────────────────────────────────────────────────────────


def test_fatiar_em_turnos_gives_one_fact_per_turn_with_optional_intermediate_asserts():
    turnos = fatiar_em_turnos(
        ["quero apartamento", "uns 3 quartos", "até 800 mil"],
        esperar_por_turno={0: {"ferramentas_proibidas": ["oferecer_imoveis"]}},
    )
    assert [t["lead"] for t in turnos] == ["quero apartamento", "uns 3 quartos", "até 800 mil"]
    assert turnos[0]["esperar"] == {"ferramentas_proibidas": ["oferecer_imoveis"]} and "esperar" not in turnos[1]
    validar_roteiro({"turnos": turnos})
    with pytest.raises(RoteiroInvalido):
        fatiar_em_turnos([])


@pytest.mark.asyncio
async def test_sharded_scenario_info_arrives_piecemeal_and_state_accumulates_across_turns():
    turnos = fatiar_em_turnos(
        ["quero comprar", "3 quartos", "ate 800 mil"],
        esperar_por_turno={
            0: {"ferramentas_proibidas": ["oferecer_imoveis"]},
            1: {"ferramentas_proibidas": ["oferecer_imoveis"]},
        },
    )
    caso = _caso(
        {"ferramentas_incluem": ["registrar_perfil", "oferecer_imoveis"], "ofertas_por_lote": 3,
         "criterios_registrados": ["intencao", "quartos", "orcamento"]},
        turnos=turnos, k=1,
    )
    driver = FakeEvalTurnDriver([
        _turno(tools=["registrar_perfil"], estado=_estado(criterios={"intencao": "compra"})),
        _turno(tools=["registrar_perfil"], estado=_estado(criterios={"intencao": "compra", "quartos": "3"})),
        _turno(
            tools=["registrar_perfil", "oferecer_imoveis"],
            estado=_estado(criterios={"intencao": "compra", "quartos": "3", "orcamento": "800k"}, lotes=(("A", "B", "C"),)),
        ),
    ])
    res = await executar_suite([caso], driver)
    assert res.aprovado, res.casos[0].execucoes[0].falhas
    # the driver saw the lead's facts one turn at a time, and the thread grew
    assert driver.mensagens_recebidas[0] == ["quero comprar", "3 quartos", "ate 800 mil"]
    assert [len(t.historico) for t in driver.threads_recebidas] == [0, 2, 4]


@pytest.mark.asyncio
async def test_an_early_offer_in_a_sharded_scenario_fails_the_intermediate_assert():
    turnos = fatiar_em_turnos(["quero comprar", "3 quartos"], esperar_por_turno={0: {"ferramentas_proibidas": ["oferecer_imoveis"]}})
    caso = _caso({"sem_violacoes": True}, turnos=turnos, k=1)
    driver = FakeEvalTurnDriver([_turno(tools=["oferecer_imoveis"]), _turno()])
    res = await executar_suite([caso], driver)
    e = res.casos[0].execucoes[0]
    assert e.status == "reprovado"
    assert [f.codigo for f in e.falhas] == ["turno1:chamada:oferecer_imoveis"]


@pytest.mark.asyncio
async def test_roteiro_fixtures_reach_the_driver_and_initial_state_is_applied():
    caso = _caso(
        {"sem_violacoes": True}, k=1,
        catalogo=[{"codigo": "AP1"}], fixture={"modo": "drenar"},
        estado_inicial={"estagio": "novo", "lotes": [["X1"]], "identificacao_faltando": ["cpf"]},
    )
    driver = FakeEvalTurnDriver([_turno()])
    await executar_suite([caso], driver)
    th = driver.threads_recebidas[0]
    assert th.catalogo == ({"codigo": "AP1"},) and th.fixture == {"modo": "drenar"}
    assert th.estado.estagio == "novo" and th.estado.lotes == (("X1",),) and th.estado.identificacao_faltando == ("cpf",)


# ── cost cap ──────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cost_cap_stops_new_executions_skips_the_rest_and_never_approves():
    caso = _caso({"sem_violacoes": True}, k=3)
    caro = com_custo(_turno(), 0.60)
    driver = FakeEvalTurnDriver([caro])
    res = await executar_suite([caso, _caso({"sem_violacoes": True}, k=3)], driver, limite_usd=1.0)
    statuses = [[e.status for e in c.execucoes] for c in res.casos]
    assert statuses == [["aprovado", "aprovado", "pulado"], ["pulado", "pulado", "pulado"]]
    assert res.orcamento_excedido and not res.completo and not res.aprovado
    assert res.custo_usd == pytest.approx(1.2)


@pytest.mark.asyncio
async def test_cost_cap_mid_execution_aborts_the_scenario_as_erro():
    caso = _caso({"sem_violacoes": True}, turnos=("a", "b", "c"), k=1)
    driver = FakeEvalTurnDriver([com_custo(_turno(), 2.0), _turno(), _turno()])
    res = await executar_suite([caso], driver, limite_usd=1.0)
    e = res.casos[0].execucoes[0]
    assert e.status == "erro" and [f.codigo for f in e.falhas] == ["excedido"]
    assert len(driver.mensagens_recebidas[0]) == 1 and res.orcamento_excedido


@pytest.mark.asyncio
async def test_no_cap_means_unbounded_and_unknown_cost_counts_as_zero():
    res = await executar_suite([_caso({"sem_violacoes": True}, k=2)], FakeEvalTurnDriver([_turno()]), limite_usd=None)
    assert res.aprovado and res.custo_usd == 0.0 and not res.orcamento_excedido


# ── failures are results, never leaks ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_driver_exception_is_an_erro_result_reporting_only_the_exception_class():
    caso = _caso({"sem_violacoes": True}, k=1)
    driver = FakeEvalTurnDriver([_turno()], erro_no_turno={(0, 0): RuntimeError("PROMPT SECRETO no traceback")})
    res = await executar_suite([caso], driver)
    e = res.casos[0].execucoes[0]
    assert e.status == "erro" and not res.aprovado
    assert [f.codigo for f in e.falhas] == ["erro_turno1:RuntimeError"]
    assert "SECRETO" not in repr(res)


@pytest.mark.asyncio
async def test_script_exhaustion_is_an_erro_not_a_pass():
    caso = _caso({"sem_violacoes": True}, turnos=("a", "b"), k=1)
    res = await executar_suite([caso], FakeEvalTurnDriver([_turno()]))
    assert res.casos[0].execucoes[0].status == "erro" and "ScriptExhausted" in res.casos[0].execucoes[0].falhas[0].codigo
    assert issubclass(ScriptExhausted, RuntimeError)


# ── publish gate decision ─────────────────────────────────────────────────────────────────────────────────


def _run(**kw) -> MecanismoGateRun:
    base = dict(
        id=uuid4(), compiled_hash="h1", status="concluida", driver="live", completa=True, aprovado=True,
        orcamento_excedido=False, total_casos=4, casos_aprovados=4,
    )
    base.update(kw)
    return MecanismoGateRun(**base)


def _req(**kw) -> MecanismoRequisito:
    base = dict(exigido=True, casos_ativos=4, run=_run())
    base.update(kw)
    return MecanismoRequisito(**base)


@pytest.mark.parametrize(
    ("req", "liberado", "codigo"),
    [
        (MecanismoRequisito(), True, "nao_exigido"),
        (_req(), True, "ok"),
        (_req(casos_ativos=0), False, "sem_casos"),
        (_req(run=None), False, "sem_execucao"),
        (_req(run=_run(compiled_hash="outro")), False, "hash_diferente"),
        (_req(run=_run(driver="fake")), False, "driver_nao_live"),
        (_req(run=_run(status="falhou")), False, "nao_concluida"),
        (_req(run=_run(orcamento_excedido=True)), False, "orcamento_excedido"),
        (_req(run=_run(completa=False)), False, "incompleta"),
        (_req(run=_run(aprovado=False, casos_aprovados=3)), False, "reprovada"),
        (_req(casos_ativos=5), False, "reprovada"),  # a case added after the run is not covered
    ],
)
def test_decidir_portao(req, liberado, codigo):
    p = decidir_portao(req, "h1")
    assert (p.liberado, p.codigo) == (liberado, codigo)
