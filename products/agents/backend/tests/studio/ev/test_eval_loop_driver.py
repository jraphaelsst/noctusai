"""The eval-loop DRIVER over the Fake store: an automatic loop opens its own rounds until a stop condition, idles with a reason when
the gate refuses, stops with `erro` + the reason when a round errors, and resumes from the DB state after a restart. The booking
(`iniciar`) is the injected seam: here it is a scripted fake that opens a round the way the route does, nothing is patched."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.notifications import FakeNotificationSink
from app.stores.studio_eval_consolidacao import FakeConsolidacaoStore
from app.stores.studio_eval_loops import FakeLoopStore
from app.studio.eval_loop_driver import LoopDriver, agendar_ao_fechar, install_driver
from app.studio.eval_loop_service import EvalLoopService, RunResumo

ORG, AGENT, OWNER = uuid4(), uuid4(), uuid4()


class Mundo:
    """A loop + a scripted 'executor': ``iniciar`` books a round (like the route), the test ends it with ``terminar``."""

    def __init__(self, *, modo="automatico", rodadas=5, orcamento=20.0):
        self.loops = FakeLoopStore()
        self.sink = FakeNotificationSink(admin_ids=["admin-1"])
        self.resumos: dict = {}
        self.recusar: HTTPException | None = None
        self.hash_atual = "h1"
        self.svc = EvalLoopService(self.loops, self.sink, FakeConsolidacaoStore(), ao_fechar=agendar_ao_fechar)
        self.loop = self.loops.create_loop(
            ORG, AGENT, agente_chave="agente-base", suite="comportamento", rodadas_planejadas=rodadas, alvo=0.95, piso=0.8,
            orcamento_usd=orcamento, started_by=OWNER, modo=modo)
        self.abertas: list = []
        self.driver = LoopDriver(servico=lambda: self.svc, iniciar=self._iniciar, ler_resumo=lambda rec, rid: self.resumos.get(rid))

    async def _iniciar(self, rec):
        if self.recusar is not None:
            raise self.recusar
        run_id = uuid4()
        self.svc.abrir(ORG, rec.id, run_id=run_id, run_tipo="comportamento", compiled_hash=self.hash_atual, partes=None)
        self.abertas.append(run_id)
        return run_id

    def terminar(self, run_id, score, *, status="concluida", custo=1.0, erro=None, erro_codigo=None, erros=()):
        self.resumos[run_id] = RunResumo(
            run_id=run_id, run_tipo="comportamento", status=status, score=score, custo_usd=custo, falhas=(),
            compiled_hash=self.hash_atual, erro=erro, erro_codigo=erro_codigo, erros=tuple(erros))

    def rec(self):
        return self.loops.get_loop(ORG, AGENT, self.loop.id)

    def avancar(self):
        return asyncio.run(self.driver.avancar(ORG, AGENT, self.loop.id))


@pytest.fixture(autouse=True)
def _sem_driver_global():
    install_driver(None)
    yield
    install_driver(None)


def test_an_automatic_loop_books_round_one_and_waits_for_it():
    m = Mundo()
    assert m.avancar() == "rodada_aberta"
    assert [r.aberta for r in m.loops.list_rodadas(ORG, m.loop.id)] == [True]
    assert m.avancar() == "rodando"  # a second pass while the round runs books nothing
    assert len(m.abertas) == 1


def test_a_manual_loop_is_never_driven():
    m = Mundo(modo="manual")
    assert m.avancar() == "inativo" and m.abertas == []


def test_it_reconciles_a_finished_round_then_books_the_next_one():
    m = Mundo()
    m.avancar()
    m.hash_atual = "h2"  # the owner edited the draft between rounds
    m.terminar(m.abertas[0], 0.6)
    assert m.avancar() == "rodada_aberta"
    assert [r.seq for r in m.loops.list_rodadas(ORG, m.loop.id)] == [1, 2] and len(m.abertas) == 2


def test_it_stops_at_the_target_and_does_not_book_another_round():
    m = Mundo()
    m.avancar()
    m.terminar(m.abertas[0], 0.97)
    assert m.avancar() == "inativo"
    assert m.rec().status == "concluido" and m.rec().motivo_parada == "alvo_atingido" and len(m.abertas) == 1


def test_it_stops_after_two_rounds_without_improvement():
    m = Mundo(rodadas=9)
    scores = [0.6, 0.6, 0.55]
    for i, sc in enumerate(scores):
        m.hash_atual = f"h{i}"
        assert m.avancar() == "rodada_aberta"
        m.terminar(m.abertas[-1], sc)
    assert m.avancar() == "inativo"
    assert m.rec().motivo_parada == "sem_melhora" and len(m.abertas) == 3


def test_it_stops_when_the_budget_is_spent():
    m = Mundo(orcamento=2.0)
    m.avancar()
    m.terminar(m.abertas[0], 0.5, custo=2.0)
    m.avancar()
    assert m.rec().motivo_parada == "orcamento_atingido"


def test_it_stops_at_the_planned_rounds():
    m = Mundo(rodadas=2)
    for i, sc in enumerate([0.5, 0.7]):
        m.hash_atual = f"h{i}"
        m.avancar()
        m.terminar(m.abertas[-1], sc)
    m.avancar()
    assert m.rec().status == "concluido" and m.rec().motivo_parada == "rodadas_esgotadas"


def test_a_round_that_errored_stops_the_loop_with_the_reason_and_books_nothing_more():
    m = Mundo()
    m.avancar()
    m.terminar(m.abertas[0], None, status="erro", erro="46 de 46 casos terminaram em erro. Primeiro erro: sem padrão",
               erro_codigo="qualificacao_indisponivel", erros=["a", "b"])
    assert m.avancar() == "inativo"
    rec = m.rec()
    assert rec.status == "parado" and rec.motivo_parada == "erro"
    assert rec.detalhe_parada["codigo"] == "qualificacao_indisponivel" and "46 de 46" in rec.detalhe_parada["mensagem"]
    [r] = m.loops.list_rodadas(ORG, m.loop.id)
    assert r.status == "erro" and r.score is None and r.erro_codigo == "qualificacao_indisponivel"
    assert "erro" in m.sink.sent[-1]["title"].lower() and len(m.abertas) == 1
    assert [e["evento"] for e in m.loops.eventos if e["evento"] in ("rodada_com_erro", "loop_parado")] == ["rodada_com_erro", "loop_parado"]


def test_an_unchanged_hash_idles_the_loop_with_the_reason_instead_of_looping():
    m = Mundo()
    m.avancar()
    m.terminar(m.abertas[0], 0.6)
    m.recusar = HTTPException(409, detail={"detail": "O conteúdo do agente não mudou.", "code": "hash_inalterado"})
    assert m.avancar() == "aguardando"
    rec = m.rec()
    assert rec.status == "ativo" and rec.aviso["codigo"] == "hash_inalterado"
    assert EvalLoopService.montar_estado(rec, m.loops.list_rodadas(ORG, m.loop.id))["estado_driver"] == "aguardando_edicao"
    m.recusar = None  # the owner fixed the content and resumed
    m.hash_atual = "h2"
    assert m.avancar() == "rodada_aberta" and m.rec().aviso is None


def test_a_preflight_refusal_stops_the_loop_with_the_turn_code():
    m = Mundo()
    m.recusar = HTTPException(409, detail={"detail": "O agente não pode ser avaliado agora: sem padrão", "code": "qualificacao_indisponivel"})
    assert m.avancar() == "erro"
    rec = m.rec()
    assert rec.status == "parado" and rec.motivo_parada == "erro" and rec.detalhe_parada["codigo"] == "qualificacao_indisponivel"
    assert m.loops.list_rodadas(ORG, m.loop.id) == [] and m.abertas == []


def test_a_crash_while_booking_stops_the_loop_with_a_reason():
    m = Mundo()

    async def quebra(rec):
        raise RuntimeError("boom")

    m.driver._iniciar = quebra
    assert m.avancar() == "erro"
    assert m.rec().motivo_parada == "erro" and m.rec().detalhe_parada["codigo"] == "driver_falhou"


def test_after_a_restart_an_orphaned_round_is_closed_as_neutral_and_the_next_round_opens():
    m = Mundo()
    m.avancar()
    orfa = m.abertas[0]
    m.terminar(orfa, None, status="cancelada")  # what ``resumo_comportamento`` maps an orphaned run to
    novo = Mundo.__new__(Mundo)  # a fresh process: only the DB state (the store) survives
    novo.__dict__.update(m.__dict__)
    novo.driver = LoopDriver(servico=lambda: m.svc, iniciar=m._iniciar, ler_resumo=lambda rec, rid: m.resumos.get(rid))

    async def retomar():
        await novo.driver.retomar_todos()
        await asyncio.gather(*list(novo.driver._tasks))

    asyncio.run(retomar())
    rodadas = m.loops.list_rodadas(ORG, m.loop.id)
    assert [(r.seq, r.status) for r in rodadas] == [(1, "cancelada"), (2, "executando")]
    assert m.rec().status == "ativo" and any(e["evento"] == "driver_retomado" for e in m.loops.eventos)


def test_the_close_hook_wakes_the_installed_driver_for_an_automatic_loop_only():
    m = Mundo()
    acordou: list = []

    class Espiao:
        def agendar(self, rec):
            acordou.append(rec.id)

    install_driver(Espiao())
    m.svc.abrir(ORG, m.loop.id, run_id=(rid := uuid4()), run_tipo="comportamento", compiled_hash="h1", partes=None)
    m.svc.fechar_por_run(ORG, RunResumo(run_id=rid, run_tipo="comportamento", status="concluida", score=0.5, custo_usd=1.0,
                                        falhas=(), compiled_hash="h1"))
    assert acordou == [m.loop.id]


def test_pausing_via_cancel_turns_an_automatic_loop_manual_and_the_driver_leaves_it_alone():
    m = Mundo()
    m.avancar()
    m.svc.pausar_se_automatico(ORG, m.abertas[0], "comportamento")
    assert m.rec().modo == "manual"
    m.terminar(m.abertas[0], None, status="cancelada")
    assert m.avancar() == "inativo" and len(m.abertas) == 1
    assert any(e["evento"] == "modo_alterado" for e in m.loops.eventos)
