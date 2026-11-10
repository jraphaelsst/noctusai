"""The runner closes a loop's round when its run ends (any way), so G3/G4/G5/G7 act mid-flight and the owner is notified."""
from __future__ import annotations

import pytest

from app.notifications import FakeNotificationSink
from app.stores.studio_definitions import SectionInput
from app.stores.studio_eval_loops import FakeLoopStore
from app.studio.eval_loop_service import EvalLoopService, KIND_PARADA
from app.studio.spec import StudioTurnTarget, build_studio_spec
from tests.studio.rt.test_evals_runner import ORG, USER, World


class LoopWorld:
    def __init__(self, *, orcamento=20.0, cases=None):
        self.w = World(**({"cases": cases} if cases else {}))
        self.loops = FakeLoopStore()
        self.sink = FakeNotificationSink(admin_ids=["owner"])
        self.svc = EvalLoopService(self.loops, self.sink, None)
        self.loop = self.loops.create_loop(ORG, self.w.agent.id, agente_chave="isa", suite="comportamento", rodadas_planejadas=30,
                                           alvo=1.0, piso=0.8, orcamento_usd=orcamento, started_by=USER)
        self.n = 0

    def mudar_conteudo(self) -> str:
        self.n += 1
        self.w.defs.replace_sections(ORG, self.w.draft.id, [SectionInput(chave="id", titulo="Id", ordem=1, conteudo=f"Você é a Isa. v{self.n}")])
        return build_studio_spec(self.w.agent, StudioTurnTarget(ORG, self.w.draft.id), definitions=self.w.defs,
                                 catalog=self.w.catalog, persist=False).compiled_hash

    async def rodada(self, *, limite_usd=None):
        h = self.mudar_conteudo()
        run = self.w.new_run(compiled_hash=h, limite_usd=limite_usd)
        self.svc.abrir(ORG, self.loop.id, run_id=run.id, run_tipo="comportamento", compiled_hash=h, partes=None)
        await self.w.runner(loops=self.svc).execute(ORG, run.id)
        return run

    def estado(self):
        return self.svc.estado(ORG, self.w.agent.id, self.loop.id)


@pytest.mark.asyncio
async def test_a_run_that_concludes_at_100_percent_closes_the_round_and_concludes_the_loop():
    lw = LoopWorld()
    await lw.rodada()
    e = lw.estado()
    assert (e["status"], e["motivo_parada"], e["melhor_score"]) == ("concluido", "alvo_atingido", 1.0)
    assert e["serie"][0]["status"] == "concluida"


@pytest.mark.asyncio
async def test_two_flat_runs_stop_the_loop_with_the_reason_and_the_failing_cases():
    lw = LoopWorld(cases=[("c1", "Pergunta 1", {"deve": ["a"], "nao_deve": []}), ("c2", "Pergunta 2", {"deve": ["a"], "nao_deve": []})])
    lw.w.judge.answers = {"Pergunta 2": [False]}  # c2 never passes: the score never moves
    for _ in range(3):  # baseline, flat #1, flat #2
        await lw.rodada()
    e = lw.estado()
    assert e["status"] == "parado" and e["motivo_parada"] == "sem_melhora"
    assert [s["overcall"] for s in e["serie"]] == [False, True, True] and e["serie"][-1]["falhas"] == ["c2"]
    [n] = lw.sink.sent
    assert n["kind"] == KIND_PARADA and "c2" in n["message"] and n["metadata"]["casos_falhando"] == ["c2"]
    assert len(set(n["metadata"]["hashes"])) == 3  # the content changed every round: it was the edits, not the re-run, that did not help


@pytest.mark.asyncio
async def test_a_cancelled_or_failed_run_closes_its_round_as_neutral():
    lw = LoopWorld()
    h = lw.mudar_conteudo()
    run = lw.w.new_run(compiled_hash="sha256:" + "f" * 64)  # hash mismatch: the run fails before judging anything
    lw.svc.abrir(ORG, lw.loop.id, run_id=run.id, run_tipo="comportamento", compiled_hash=h, partes=None)
    await lw.w.runner(loops=lw.svc).execute(ORG, run.id)
    e = lw.estado()
    assert e["status"] == "ativo" and e["serie"][0]["status"] == "falhou" and e["serie"][0]["score"] is None
    assert e["serie"][0]["overcall"] is False


@pytest.mark.asyncio
async def test_a_run_without_a_loop_is_untouched():
    lw = LoopWorld()
    run = lw.w.new_run()
    await lw.w.runner(loops=lw.svc).execute(ORG, run.id)
    assert lw.loops.list_rodadas(ORG, lw.loop.id) == [] and lw.sink.sent == []


class _StoreQuebrado(FakeLoopStore):
    def rodada_do_run(self, *a, **k):
        raise RuntimeError("db down")


@pytest.mark.asyncio
async def test_a_broken_loop_store_never_fails_the_finished_run(caplog):
    lw = LoopWorld()
    svc = EvalLoopService(_StoreQuebrado(), lw.sink, None)  # injected through the seam, nothing patched
    run = lw.w.new_run()
    await lw.w.runner(loops=svc).execute(ORG, run.id)
    assert lw.w.run_row(run.id).status == "concluida"
    assert "fechar_rodada_falhou" in caplog.text
