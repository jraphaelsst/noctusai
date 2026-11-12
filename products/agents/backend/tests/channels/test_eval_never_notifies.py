"""An eval never notifies anyone, BY CONSTRUCTION: the live driver injects Fakes and every Real notifier refuses
inside an eval scope. Opt-out and alert run through the live-driver wiring (model scripted)."""
from __future__ import annotations

import asyncio

import pytest
from noctusai_lib.integrations.llm import FakeProvider

from app.notifications import EvalSideEffectRefused, SupabaseNotificationSink, eval_scope, get_notification_sink
from app.studio.catalog import StoreKnowledgeCatalog
from app.studio.eval_driver import ThreadState
from app.studio.eval_driver_live import LiveEvalTurnDriver
from tests.channels.conftest import ORG_KEY
from tests.channels.test_julia_v2_e2e import call, say, step


def _driver(chan, provider):
    return LiveEvalTurnDriver(
        studio_store=chan.rt.studio, catalog=StoreKnowledgeCatalog(chan.rt.knowledge), padroes=chan.padroes,
        agent_key="julia", key_resolver=lambda provider_name, org: ORG_KEY, provider_impl=provider)


class TestEvalNeverNotifies:
    def test_opt_out_and_alert_land_on_the_fake_never_a_real_sink(self, chan):
        chan.seed_agent(publish=False)
        provider = FakeProvider(tool_responses=[
            step(call("sinalizar_alerta", tipo="outro", descricao="lead irritado")), say("ok"),
            step(call("encerrar", motivo="lead_pediu_parar", motivo_texto="pediu para parar",
                      trecho="pare de me mandar mensagens")),
            say("Tudo bem."),
        ])
        driver = _driver(chan, provider)
        thread = ThreadState()
        asyncio.run(driver.executar_turno(thread, "oi"))
        asyncio.run(driver.executar_turno(thread, "pare de me mandar mensagens"))
        mundo = driver._mundo
        assert [n["kind"] for n in mundo.svc.notificacoes.sent] == ["agents.lead_opt_out"]
        eventos = mundo.threads.listar_opt_out_eventos(mundo.org_id, limit=10, cursor=None, lead_ref_id=None)[0]
        assert [e.notificacao_status for e in eventos] == ["enviada"]  # not "falhou" / SemDestinatarios

    def test_a_real_notifier_cannot_be_built_inside_an_eval(self):
        with eval_scope():
            with pytest.raises(EvalSideEffectRefused):
                get_notification_sink()
            with pytest.raises(EvalSideEffectRefused):
                SupabaseNotificationSink(lambda: None)

    def test_a_real_sink_built_outside_refuses_every_call_inside(self):
        def boom():
            raise AssertionError("core client reached")
        sink = SupabaseNotificationSink(boom)
        with eval_scope():
            for fn in (lambda: sink.platform_admin_ids(), lambda: sink.org_admin_ids(None),
                       lambda: sink.already_sent("u", "k"), lambda: sink.user_label("u"),
                       lambda: sink.send("u", kind="k", title="t", message="m", metadata={})):
                with pytest.raises(EvalSideEffectRefused):
                    fn()
