"""The eval-loop gate's WhatsApp notice to the owner: a stop and a checkpoint each send ONE scripted text from the owner line
(seed ``notify_owner``, catalog kinds ``eval_loop_parada`` / ``eval_loop_checkpoint``), next to the in-app bell.

The send is injected through ``EvalLoopService(avisar_dono=...)``; nothing is patched. Once per transition: the round close
that triggers it is a conditional write, so a retried close never re-sends."""
from __future__ import annotations

from functools import partial
from uuid import uuid4

from noctusai_lib.domain.notification_catalog import (
    FakeNotificationGate,
    FakeOwnerLineTransport,
    FakeOwnerRecipientSource,
    OwnerRecipient,
    configure_owner_line,
    get_owner_line,
    notify_owner,
)

from app.notification_kinds import KIND_EVAL_LOOP_CHECKPOINT, KIND_EVAL_LOOP_PARADA
from app.notifications import FakeNotificationSink
from app.stores.studio_eval_consolidacao import FakeConsolidacaoStore
from app.stores.studio_eval_loops import FakeLoopStore
from app.studio.eval_loop_service import EvalLoopService, RunResumo

ORG, AGENT, OWNER = uuid4(), uuid4(), uuid4()


class Recorder:
    def __init__(self, *, falha: bool = False):
        self.calls: list[dict] = []
        self.falha = falha

    def __call__(self, product, kind, texto, *, org_id=None):
        self.calls.append({"product": product, "kind": kind, "texto": texto, "org_id": org_id})
        if self.falha:
            raise RuntimeError("linha fora do ar")


class W:
    def __init__(self, avisar, *, rodadas=30):
        self.loops = FakeLoopStore()
        self.sink = FakeNotificationSink(admin_ids=["admin-1"])
        self.svc = EvalLoopService(self.loops, self.sink, FakeConsolidacaoStore(), avisar_dono=avisar)
        self.loop = self.loops.create_loop(ORG, AGENT, agente_chave="julia", suite="comportamento", rodadas_planejadas=rodadas,
                                           alvo=1.0, piso=0.8, orcamento_usd=20.0, started_by=OWNER)

    def rodada_fechada(self, h, score, *, custo=1.0):
        run_id = uuid4()
        self.svc.abrir(ORG, self.loop.id, run_id=run_id, run_tipo="comportamento", compiled_hash=h, partes=None)
        resumo = RunResumo(run_id=run_id, run_tipo="comportamento", status="concluida", score=score, custo_usd=custo,
                           falhas=("caso-a",), compiled_hash=h)
        d = self.svc.fechar_por_run(ORG, resumo)
        return d, resumo

    def parar_sem_melhora(self):
        for i, s in enumerate((0.6, 0.7, 0.7, 0.69), start=1):
            d, resumo = self.rodada_fechada(f"h{i}", s)
        return d, resumo


def test_a_stop_sends_one_scripted_whatsapp_to_the_owner_beside_the_bell():
    rec = Recorder()
    w = W(rec)
    d, _ = w.parar_sem_melhora()
    assert d.parada.motivo == "sem_melhora"
    [c] = rec.calls
    assert (c["product"], c["kind"], c["org_id"]) == ("agents", KIND_EVAL_LOOP_PARADA, ORG)
    for part in ("julia", "comportamento", "2 rodadas seguidas sem melhora", "70%", "US$ 4.00", "US$ 20.00", "/agentes"):
        assert part in c["texto"]
    assert len(w.sink.sent) == 1  # the bell still rings


def test_a_retried_close_of_the_same_run_does_not_send_again():
    rec = Recorder()
    w = W(rec)
    _, resumo = w.parar_sem_melhora()
    assert w.svc.fechar_por_run(ORG, resumo) is None
    assert len(rec.calls) == 1


def test_a_checkpoint_sends_the_checkpoint_kind():
    rec = Recorder()
    w = W(rec)
    for i, s in enumerate((0.5, 0.6, 0.7, 0.8, 0.85), start=1):  # improving every round: no stop, checkpoint at 5
        w.rodada_fechada(f"h{i}", s)
    [c] = rec.calls
    assert c["kind"] == KIND_EVAL_LOOP_CHECKPOINT
    assert "rodada 5 de 30" in c["texto"] and "85%" in c["texto"]


def test_a_failing_owner_line_never_undoes_the_stop_or_the_bell():
    w = W(Recorder(falha=True))
    d, _ = w.parar_sem_melhora()
    assert d.parada.motivo == "sem_melhora"
    assert w.svc.estado(ORG, AGENT, w.loop.id)["status"] == "parado"
    assert len(w.sink.sent) == 1


def test_through_the_real_notify_owner_a_stop_is_sent_and_recorded():
    gate = FakeNotificationGate(product="agents")
    transport = FakeOwnerLineTransport()
    ok = partial(notify_owner, gate=gate, recipients=FakeOwnerRecipientSource([OwnerRecipient("+5511999990001")]),
                 transport=transport)
    W(ok).parar_sem_melhora()
    assert [s["status"] for s in gate.sends] == ["sent"] and len(transport.sent) == 1



def test_with_the_noc_line_not_configured_the_stop_records_failed_not_silence():
    """L3 not bought yet: the installed line has recipients but no transport (NOC_OWNER_LINE_WAHA_URL unset)."""
    antes = get_owner_line()
    configure_owner_line(recipients=FakeOwnerRecipientSource([OwnerRecipient("+5511999990001")]), transport=None)
    try:
        gate = FakeNotificationGate(product="agents")
        W(partial(notify_owner, gate=gate)).parar_sem_melhora()
        [s] = gate.sends
        assert s["status"] == "failed" and s["reason"] == "linha_noc_nao_configurada"
    finally:
        configure_owner_line(recipients=antes.recipients, transport=antes.transport)
