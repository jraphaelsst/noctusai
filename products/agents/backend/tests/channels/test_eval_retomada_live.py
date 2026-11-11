"""The live driver's follow-up turn (``executar_retomada``) over a scripted provider: the REAL turn path, no model."""
from __future__ import annotations

import asyncio

import pytest
from noctusai_lib.integrations.llm import FakeProvider

from app.studio.catalog import StoreKnowledgeCatalog
from app.studio.eval_driver import Retomada, RetomadaCapIndisponivel, ThreadState
from app.studio.eval_driver_live import LiveEvalTurnDriver
from tests.channels.conftest import ORG_KEY
from tests.channels.test_julia_v2_e2e import say


def _driver(chan, provider):
    return LiveEvalTurnDriver(
        studio_store=chan.rt.studio, catalog=StoreKnowledgeCatalog(chan.rt.knowledge), padroes=chan.padroes,
        agent_key="julia", key_resolver=lambda provider_name, org: ORG_KEY, provider_impl=provider)


class TestLiveDriver:
    def test_the_follow_up_texts_render_and_no_lead_message_is_added(self, chan):
        chan.seed_agent(publish=False)
        provider = FakeProvider(tool_responses=[say("Oi!"), say("Oi, ainda procura imóvel?")])
        driver = _driver(chan, provider)
        thread = ThreadState()
        asyncio.run(driver.executar_turno(thread, "oi"))
        out = asyncio.run(driver.executar_retomada(thread, Retomada(tier="horas", texto_base="Oi, ainda procura imóvel?")))
        assert out.retomada_status == "normal" and out.retomada_tier == "horas"
        assert out.bolhas == ("Oi, ainda procura imóvel?",)
        last = [c for c in provider.calls if c["method"] == "chat_with_tools"][-1]["messages"]
        assert [m.role for m in last if m.role != "system"] == ["user", "assistant"]  # history only: no fake lead message
        sistema = "\n".join(str(m.content) for m in last if m.role == "system")
        assert "txt:reengajamento.horas" in sistema and "Oi, ainda procura imóvel?" in sistema

    def test_a_follow_up_with_no_thread_is_ignored_and_says_so(self, chan):
        chan.seed_agent(publish=False)
        provider = FakeProvider(tool_responses=[say("nunca")])
        out = asyncio.run(_driver(chan, provider).executar_retomada(ThreadState(), Retomada(tier="horas")))
        assert out.retomada_status == "reengajamento_ignorado" and out.bolhas == ()
        assert not [c for c in provider.calls if c["method"] == "chat_with_tools"]

    def test_a_seeded_cap_is_refused(self, chan):
        chan.seed_agent(publish=False)
        driver = _driver(chan, FakeProvider(tool_responses=[say("x")]))
        with pytest.raises(RetomadaCapIndisponivel):
            asyncio.run(driver.executar_retomada(ThreadState(), Retomada(tier="horas", seguidas_previas=1)))
