"""``fixture.retomada`` + the ``retomada`` roteiro turn: a follow-up (re-engagement) turn is testable in evals.
Fixtures are synthetic. The cap (``seguidas_previas`` > 0, ``retomada_status: limite_retomadas``) waits for the
store of ``feat/agents-retomada-limite`` (NOC-REMEDIATE[retomada-cap-assert]) and is REFUSED, never passed."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.studio.eval_driver import (
    Estado, FakeEvalTurnDriver, Retomada, RetomadaCapIndisponivel, ThreadState, TurnOutcome,
)
from app.studio.eval_mecanismo import (
    AssertInvalido, Caso, RoteiroInvalido, executar_suite, validar_asserts, validar_caso_mecanismo,
    validar_mundo_juiz, validar_roteiro,
)

BASE = {"turnos": [{"lead": "oi"}]}


class TestValidacao:
    def test_a_valid_fixture_and_turn_pass_both_suites(self):
        fx = {"retomada": {"tier": "regua", "texto_base": "Oi, ainda procura imóvel?", "seguidas_previas": 0}}
        roteiro = {"turnos": [{"lead": "oi"}, {"retomada": True}, {"retomada": {"tier": "minutos"}, "esperar": {"sem_resposta": True}}], "fixture": fx}
        validar_roteiro(roteiro)
        validar_caso_mecanismo(k=1, roteiro=roteiro, asserts={"retomada_status": "normal"})
        validar_mundo_juiz({"fixture": fx})

    def test_a_turn_cannot_be_a_lead_message_and_a_follow_up(self):
        with pytest.raises(RoteiroInvalido):
            validar_roteiro({"turnos": [{"lead": "oi", "retomada": True}]})

    @pytest.mark.parametrize("turno", [
        {"retomada": False}, {"retomada": "horas"}, {"retomada": {"tier": "dias"}},
        {"retomada": {"tier": "horas", "extra": 1}}, {"retomada": {"texto_base": ""}},
        {"retomada": {"texto_base": "x" * 501}}, {"esperar": {"sem_resposta": True}},
    ])
    def test_a_malformed_follow_up_turn_is_refused(self, turno):
        with pytest.raises(RoteiroInvalido):
            validar_roteiro({"turnos": [turno]})

    @pytest.mark.parametrize("retomada", [
        {"tier": "dias"}, {"seguidas_previas": 6}, {"seguidas_previas": -1}, {"seguidas_previas": True},
        {"texto_base": "x" * 501}, {"outro": 1}, "horas",
    ])
    def test_a_malformed_fixture_is_refused_by_both_suites(self, retomada):
        with pytest.raises(RoteiroInvalido):
            validar_roteiro({**BASE, "fixture": {"retomada": retomada}})
        with pytest.raises(RoteiroInvalido):
            validar_mundo_juiz({"fixture": {"retomada": retomada}})

    def test_the_asserts_are_closed(self):
        validar_asserts({"retomada_status": "reengajamento_ignorado", "retomada_tier_usado": "horas"})
        with pytest.raises(AssertInvalido):
            validar_asserts({"retomada_tier_usado": "dias"})
        with pytest.raises(AssertInvalido):
            validar_asserts({"retomada_status": "talvez"})

    def test_the_cap_assert_is_refused_until_its_store_exists(self):
        with pytest.raises(AssertInvalido, match="retomada-cap-assert"):
            validar_asserts({"retomada_status": "limite_retomadas"})


def _caso(turnos, asserts, **roteiro) -> Caso:
    return Caso(id=uuid4(), slug="c", k=1, roteiro={"turnos": turnos, **roteiro}, asserts=asserts)


class TestScriptedDriver:
    def test_a_follow_up_turn_runs_end_to_end_and_the_asserts_read_it(self):
        driver = FakeEvalTurnDriver([
            TurnOutcome(bolhas=("Oi!",), estado=Estado()),
            TurnOutcome(bolhas=("Oi, ainda procura imóvel?",), estado=Estado()),
        ])
        caso = _caso(
            [{"lead": "oi"}, {"retomada": {"tier": "regua", "texto_base": "Oi, ainda procura?"}, "esperar": {"retomada_tier_usado": "regua", "retomada_status": "normal"}}],
            {"retomada_tier_usado": "regua", "retomada_status": "normal"},
            fixture={"retomada": {"tier": "horas"}})
        res = asyncio.run(executar_suite([caso], driver))
        assert res.casos[0].execucoes[0].status == "aprovado", res.casos[0].execucoes[0].falhas
        assert driver.retomadas_recebidas == [Retomada(tier="regua", texto_base="Oi, ainda procura?")]
        assert [m.role for m in driver.threads_recebidas[1].historico] == ["lead", "agente"]

    def test_the_fixture_supplies_the_default_tier(self):
        driver = FakeEvalTurnDriver([TurnOutcome(bolhas=("a",)), TurnOutcome(bolhas=("b",))])
        caso = _caso([{"lead": "oi"}, {"retomada": True}], {"retomada_tier_usado": "minutos"},
                     fixture={"retomada": {"tier": "minutos"}})
        res = asyncio.run(executar_suite([caso], driver))
        assert res.casos[0].execucoes[0].status == "aprovado"

    def test_a_wrong_tier_fails_the_assert(self):
        driver = FakeEvalTurnDriver([TurnOutcome(bolhas=("a",))])
        caso = _caso([{"retomada": True}], {"retomada_tier_usado": "regua"})
        res = asyncio.run(executar_suite([caso], driver))
        ex = res.casos[0].execucoes[0]
        assert ex.status == "reprovado" and ex.falhas[0].codigo == "esperado:regua|obtido:horas"

    def test_a_seeded_cap_is_refused_not_passed(self):
        driver = FakeEvalTurnDriver([TurnOutcome(bolhas=("a",))])
        caso = _caso([{"retomada": True}], {"sem_resposta": True}, fixture={"retomada": {"seguidas_previas": 2}})
        ex = asyncio.run(executar_suite([caso], driver)).casos[0].execucoes[0]
        assert ex.status == "erro" and ex.falhas[0].codigo == "erro_turno1:RetomadaCapIndisponivel"
        with pytest.raises(RetomadaCapIndisponivel):
            asyncio.run(driver.executar_retomada(ThreadState(), Retomada(tier="horas", seguidas_previas=2)))

    def test_a_driver_without_the_follow_up_hook_is_an_error_result(self):
        class Velho:
            tipo = "fake"

            async def executar_turno(self, thread, mensagem_lead):
                return TurnOutcome()

        ex = asyncio.run(executar_suite([_caso([{"retomada": True}], {"sem_resposta": True})], Velho())).casos[0].execucoes[0]
        assert ex.status == "erro" and ex.falhas[0].codigo == "erro_turno1:AttributeError"
