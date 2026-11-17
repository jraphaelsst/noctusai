"""An agent WITHOUT a qualification standard (a base layer): the eval path runs it (no qualification tools, no scoring);
a production channel turn still refuses it."""
from __future__ import annotations

import asyncio

from noctusai_lib.integrations.llm import FakeProvider

from app.qualificacao.models import ID_PADRAO_NULO, e_padrao_nulo, padrao_nulo
from app.studio.catalog import StoreKnowledgeCatalog
from app.studio.eval_driver import ThreadState
from app.studio.eval_driver_live import LiveEvalTurnDriver
from tests.channels.conftest import ORG_KEY
from tests.channels.test_julia_v2_e2e import say


def _sem_padrao(chan, publish=False):
    chan.seed_agent(publish=publish)
    d = chan.rt.studio.get_platform_definition("julia")
    from dataclasses import replace

    store = chan.rt.studio
    store._agents[(d.org_id, "julia")] = replace(d, padrao_qualificacao=None)  # the Fake's row: the definition declares none
    return d


def _driver(chan, provider):
    return LiveEvalTurnDriver(
        studio_store=chan.rt.studio, catalog=StoreKnowledgeCatalog(chan.rt.knowledge), padroes=chan.padroes,
        agent_key="julia", key_resolver=lambda provider_name, org: ORG_KEY, provider_impl=provider)


class TestSemPadrao:
    def test_the_null_standard_is_empty_and_marked(self):
        p = padrao_nulo()
        assert e_padrao_nulo(p) and p.id == ID_PADRAO_NULO and p.criterios == () and [e.conclusivo for e in p.estagios] == [False]

    def test_the_eval_driver_runs_an_agent_that_declares_no_standard(self, chan):
        _sem_padrao(chan)
        provider = FakeProvider(tool_responses=[say("Olá, tudo bem?")])
        out = asyncio.run(_driver(chan, provider).executar_turno(ThreadState(), "oi"))
        assert out.bolhas == ("Olá, tudo bem?",)
        assert out.estado.estagio == "sem_qualificacao" and out.estado.criterios == {}
        oferecidas = {t["function"]["name"] if isinstance(t, dict) and "function" in t else getattr(t, "name", str(t))
                      for c in provider.calls if c["method"] == "chat_with_tools" for t in (c.get("tools") or [])}
        assert not {"registrar_perfil", "avaliar_lead", "concluir_qualificacao"} & oferecidas

    def test_a_production_channel_turn_still_refuses_it(self, chan):
        _sem_padrao(chan, publish=True)
        resp = chan.turn()
        assert resp.status_code == 409 and resp.json()["code"] == "qualificacao_indisponivel"
