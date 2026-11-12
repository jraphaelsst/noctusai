"""A judge case of a channel agent runs on the real channel path (``EvalTurnDriver``), with its ``contexto`` in the STATE block
and never in the lead's turn (Julia turn redesign)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.studio.eval_driver import TurnOutcome, Violation
from app.studio.evals import EvalRunner


class _Driver:
    def __init__(self, bolhas=("Oi!",), acoes=(), violacoes=()):
        self.chamadas = []
        self._out = TurnOutcome(bolhas=tuple(bolhas), acoes=tuple(acoes), violacoes=tuple(violacoes), custo_usd=0.01)

    def definir_agente(self, key): self.agente = key
    def nova_execucao(self): pass
    def definir_modelo(self, m): self.modelo = m

    async def executar_turno(self, thread, mensagem):
        self.chamadas.append((thread, mensagem))
        return self._out


def _runner(driver, usa_canais=True):
    r = EvalRunner(evals=None, runs=None, definitions=None, catalog=None, runtime=None, broker=None, judge=None,
                   instance_id="t", turn_driver_factory=lambda: driver)
    r._agente = SimpleNamespace(key="julia", usa_canais=usa_canais)
    return r


CASO = SimpleNamespace(entrada="Quero visitar sábado", contexto="O lead já viu o imóvel ONE9001.",
                       roteiro={"estado_inicial": {"criterios": {"operacao": "compra"}}, "fixture": {"specs": {"x": "y"}}})
RUN = SimpleNamespace(id="run-1", modelo_geracao=None)
SPEC = SimpleNamespace(runtime="llm")


def test_the_context_goes_to_the_state_block_and_the_user_turn_is_the_leads_own_text():
    d = _Driver()
    saida, _custo = asyncio.run(_runner(d)._resposta_pelo_canal(RUN, SPEC, CASO))
    [(thread, mensagem)] = d.chamadas
    assert mensagem == "Quero visitar sábado" and "<nota do sistema>" not in mensagem
    assert thread.contexto_caso == "O lead já viu o imóvel ONE9001."
    assert thread.estado.criterios == {"operacao": "compra"} and thread.fixture == {"specs": {"x": "y"}}
    assert saida == "Oi!"


def test_a_non_channel_agent_or_a_process_without_a_driver_keeps_the_old_path():
    assert asyncio.run(_runner(_Driver(), usa_canais=False)._resposta_pelo_canal(RUN, SPEC, CASO)) is None
    r = _runner(None)
    r._turn_driver_factory = None
    assert asyncio.run(r._resposta_pelo_canal(RUN, SPEC, CASO)) is None


def test_an_empty_reply_says_why_in_codes_only():
    from app.studio.evals import _CaseError

    d = _Driver(bolhas=(), acoes=("handoff",), violacoes=(Violation("vazamento_prompt", "bloqueada"),))
    with pytest.raises(_CaseError) as exc:
        asyncio.run(_runner(d)._resposta_pelo_canal(RUN, SPEC, CASO))
    assert "handoff" in str(exc.value) and "vazamento_prompt:bloqueada" in str(exc.value)


# ── templates (``modelo``): never on a channel, but judged on the SAME lead-facing path ─────────────────────────────────
# prod judge runs 97db817b (agente-base) / c4c4be57 (sdr-base): a template is no channel agent (073: never owned by a channel
# product), so it fell to the legacy path -- no channel tools, no skills (``skills=()``), specs only as ``[dado: x]`` pointers. The
# model narrated "abrindo a skill ..." (judged as the answer) and echoed raw slots (``erro: placeholder cru``).

def _template_runner(driver):
    r = _runner(driver, usa_canais=False)
    r._agente = SimpleNamespace(key="sdr-base", usa_canais=False, modelo=True)
    return r


def test_a_template_runs_on_the_channel_path_with_its_fixture_specs():
    d = _Driver(bolhas=("Oi! Posso ajudar com a busca.",))
    saida, _ = asyncio.run(_template_runner(d)._resposta_pelo_canal(RUN, SPEC, CASO))
    [(thread, _msg)] = d.chamadas
    assert saida == "Oi! Posso ajudar com a busca." and thread.fixture == {"specs": {"x": "y"}}


def test_a_template_whose_runtime_is_not_llm_still_takes_the_channel_path():
    # the channel turn always runs on the neutral runtime (``preparar`` forces it); a template is judged as its children run
    d = _Driver()
    assert asyncio.run(_template_runner(d)._resposta_pelo_canal(RUN, SimpleNamespace(runtime="claude_sdk"), CASO)) is not None


def test_a_non_template_non_channel_agent_still_keeps_the_old_path():
    r = _runner(_Driver(), usa_canais=False)
    r._agente = SimpleNamespace(key="x", usa_canais=False, modelo=False)
    assert asyncio.run(r._resposta_pelo_canal(RUN, SPEC, CASO)) is None


@pytest.mark.parametrize("bolha", ["Prazo: {{org.prazo}}", "Veja [dado: prazo]"])
def test_a_raw_placeholder_in_the_final_reply_is_never_judged_for_any_agent(bolha):
    from app.studio.evals import _CaseError

    with pytest.raises(_CaseError, match="placeholder cru"):
        asyncio.run(_runner(_Driver(bolhas=(bolha,)))._resposta_pelo_canal(RUN, SPEC, CASO))
    with pytest.raises(_CaseError, match="placeholder cru"):
        asyncio.run(_template_runner(_Driver(bolhas=(bolha,)))._resposta_pelo_canal(RUN, SPEC, CASO))
