"""Julia turn redesign (``projects/julia-v2/DECISAO-SKILL-AUTOLOAD.md``): compile cache + byte-stable system message 1,
the greeting regression guard, the corrective re-run's fresh counters, the version-level temperature."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from noctusai_lib.integrations.llm import FakeProvider

from app.channels import turno as turno_mod
from app.channels.tool_registry import JuliaTurno
from tests.channels.conftest import turn_body
from tests.channels.test_julia_v2_e2e import call, say, step, tool_results
from tests.channels.test_julia_v2_gates import gated  # noqa: F401 -- fixture


def _system1(provider: FakeProvider) -> list[str]:
    out = []
    for c in provider.calls:
        if c["method"] == "chat_with_tools":
            first = c["messages"][0]
            out.append(first.content if hasattr(first, "content") else first["content"])
    return out


class TestCompileCacheAndStablePrefix:
    def test_two_consecutive_turns_share_system_message_1_and_do_not_recompile_or_resave(self, gated):  # noqa: F811
        chan = gated
        turno_mod.limpar_cache_compilacao()
        base = dict(turno_mod.ESTATISTICAS)
        chan.use_provider(FakeProvider(tool_responses=[say("Oi! Tudo bem?")]))
        chan.turn(turn_body("Oi", ids=["a"]))
        primeira = _system1(chan.provider)
        assert dict(turno_mod.ESTATISTICAS)["compilou"] - base["compilou"] >= 1
        assert dict(turno_mod.ESTATISTICAS)["salvou_prompt"] - base["salvou_prompt"] == 1
        meio = dict(turno_mod.ESTATISTICAS)

        chan.use_provider(FakeProvider(tool_responses=[say("Qual o bairro?")]))
        chan.turn(turn_body("Quero comprar", ids=["b"]))
        segunda = _system1(chan.provider)
        depois = dict(turno_mod.ESTATISTICAS)
        assert depois["compilou"] == meio["compilou"]  # no recompile
        assert depois["salvou_prompt"] == meio["salvou_prompt"]  # no new proof-of-use write
        assert depois["reaproveitou"] > meio["reaproveitou"]
        assert primeira and segunda and primeira[0] == segunda[0]  # byte-identical system message 1

    def test_a_draft_is_never_cached(self, gated):  # noqa: F811
        """Eval runs compile a DRAFT that changes under the key: the cache holds PUBLISHED versions only."""
        import inspect

        assert '("ativa", "substituida")' in inspect.getsource(turno_mod._compilar)


class TestGreetingNeverHandsOff:
    @pytest.mark.parametrize("k", range(5))
    def test_oi_vi_o_anuncio_with_every_tool_called_early_has_zero_handoff_and_zero_limite_recusas(self, gated, k):  # noqa: F811
        """The prod regression (a greeting handed the lead off): tools tied to skills are called before anything is
        'opened'; with auto-load none of it is a refusal."""
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[
            step(call("oferecer_imoveis", modo="campanha"), call("registrar_perfil", itens=[
                {"criterio": "operacao", "valor": "compra", "trecho": "Oi, vi o anúncio"}])),
            step(call("avaliar_lead")),
            say("Oi! Que bom que você viu o anúncio. Em que posso ajudar?")]))
        body = chan.turn(turn_body("Oi, vi o anúncio", ids=[f"g{k}"])).json()
        assert body["status"] == "respondido"
        assert not [a for a in body["actions"] if a["type"] == "handoff"]
        assert "limite_recusas" not in str(body) and "skill_nao_aberta" not in str(tool_results(chan.provider))


class TestFreshAttempt:
    def test_a_rerun_starts_with_fresh_budgets_and_loaded_skills(self):
        t = SimpleNamespace(
            recusas=2, erros=1, chamadas=7, chamadas_por_ferramenta={"a": 3}, skills_carregadas={"s"},
            parar="limite_recusas", recusas_anteriores=0)
        JuliaTurno.reiniciar_tentativa(t)
        assert (t.recusas, t.erros, t.chamadas, t.chamadas_por_ferramenta, t.skills_carregadas, t.parar) == (
            0, 0, 0, {}, set(), None)
        assert t.recusas_anteriores == 2


class TestTemperature:
    def test_default_is_low_and_the_version_can_override_within_bounds(self):
        v = lambda tp: SimpleNamespace(tool_policy=tp)  # noqa: E731
        assert turno_mod.temperatura_da_versao(v({})) == turno_mod.TEMPERATURA_CANAL_PADRAO == 0.3
        assert turno_mod.temperatura_da_versao(v({"temperature": 0.8})) == 0.8
        assert turno_mod.temperatura_da_versao(v({"temperature": 7})) == 1.0
        assert turno_mod.temperatura_da_versao(v({"temperature": True})) == 0.3
        assert turno_mod.temperatura_da_versao(v({"temperature": "x"})) == 0.3

    def test_the_turn_reaches_the_provider_with_the_channel_temperature(self, gated):  # noqa: F811
        chan = gated
        chan.use_provider(FakeProvider(tool_responses=[say("Oi!")]))
        chan.turn(turn_body("Oi", ids=["t"]))
        c = next(c for c in chan.provider.calls if c["method"] == "chat_with_tools")
        assert c["temperature"] == 0.3
