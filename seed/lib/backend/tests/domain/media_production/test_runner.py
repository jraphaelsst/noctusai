from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from noctusai_lib.domain.jobs import FakeJobRepository, RetryPolicy, Worker
from noctusai_lib.domain.media_production import (
    BusProgress,
    FakeLedger,
    FakeMover,
    FakeProgress,
    FakeQuota,
    GraphSpec,
    MediaGraphRunner,
    StepError,
    StepRegistry,
    StepResult,
    StepSpec,
    vendor_cost_row,
    vendor_credit_usd,
)
from noctusai_lib.realtime.bus import FakeRealtimeBus

ORG, POST = "org-1", "post-1"


def run(coro):
    return asyncio.run(coro)


def build(quota=None, fail_render=False, quota_estimate=None):
    reg = StepRegistry()
    calls: list[str] = []

    async def tts(ctx):
        calls.append("tts")
        return StepResult(
            saida={"audio": "a.mp3"}, vendor="fake-tts", modelo="v1", request_id="r1",
            unidades={"caracteres": 120, "audio_s": 8.0, "creditos_cobrados": 120},
            custo_usd=vendor_credit_usd(120, Decimal("0.0001")),
        )

    async def render(ctx):
        calls.append("render")
        if fail_render:
            raise StepError("render_falhou")
        assert ctx.entradas["tts"] == {"audio": "a.mp3"}
        return StepResult(saida={"video": "v.mp4"}, medicoes={"video_s": 8.0})

    async def mux(ctx):
        calls.append("mux")
        return StepResult(saida={"final": "f.mp4"}, vendor="fake-mux")

    reg.register_step("tts", tts)
    reg.register_step("render", render)
    reg.register_step("mux", mux)
    repo = FakeJobRepository()
    ledger, progress, mover = FakeLedger(), FakeProgress(), FakeMover()
    runner = MediaGraphRunner(
        jobs=repo, ledger=ledger, progress=progress, quota=quota or FakeQuota(),
        mover=mover, registry=reg, max_retries=0,
    )
    worker = Worker(repo, worker_id="w1", handlers=runner.handlers,
                    retry_policy=RetryPolicy(max_retries=0, backoff_seconds=0))
    graph = GraphSpec(ORG, POST, (
        StepSpec("tts", "Sintetizando voz", peso=2, estimativa_usd=quota_estimate),
        StepSpec("render", "Renderizando vídeo", ("tts",), peso=6),
        StepSpec("mux", "Finalizando", ("render",), peso=2),
    ))
    return runner, worker, ledger, progress, mover, calls, graph


async def drain(worker):
    while await worker.run_once():
        pass


def test_three_step_graph_end_to_end() -> None:
    runner, worker, ledger, progress, mover, calls, graph = build()

    async def go():
        await runner.enqueue_graph(graph)
        # only the root is released before it completes
        assert await worker.run_once() and calls == ["tts"]
        await drain(worker)

    run(go())
    assert calls == ["tts", "render", "mux"]
    rows = {r.passo: r for r in ledger.rows.values()}
    assert all(r.status == "concluido" for r in rows.values())
    assert rows["tts"].custo_usd == Decimal("0.012000")
    assert rows["tts"].unidades["caracteres"] == 120 and rows["tts"].request_id == "r1"
    assert rows["render"].custo_usd is None and rows["render"].nao_medido == ()
    assert rows["mux"].vendor == "fake-mux"
    assert rows["mux"].nao_medido == ("custo_usd", "unidades")  # unmeasured, never estimated
    assert rows["render"].duracao_s is not None and rows["render"].cpu_s is not None
    msgs = [e.message for e in progress.events]
    assert msgs[0] == "Sintetizando voz (1/3)"
    assert "Renderizando vídeo (2/3)" in msgs and "Finalizando (3/3)" in msgs
    assert msgs[-1] == "Criação concluída" and progress.events[-1].terminal
    weights = [round(e.progress, 2) for e in progress.events]
    assert weights == [0.0, 0.2, 0.8, 1.0]
    assert mover.movimentos == [(POST, "criacao_concluida")]


def test_failure_stops_graph_visibly() -> None:
    runner, worker, ledger, progress, mover, calls, graph = build(fail_render=True)

    async def go():
        await runner.enqueue_graph(graph)
        await drain(worker)

    run(go())
    assert calls == ["tts", "render"]  # mux never ran
    rows = {r.passo: r for r in ledger.rows.values()}
    assert rows["render"].status == "falhou" and rows["render"].erro_codigo == "render_falhou"
    assert rows["mux"].status == "cancelado"
    assert progress.events[-1].terminal and "Falhou: Renderizando vídeo (render_falhou)" == progress.events[-1].message
    assert mover.movimentos == [(POST, "passo_falhou")]


def test_quota_refusal_is_falhou_cota() -> None:
    runner, worker, ledger, progress, mover, calls, graph = build(
        quota=FakeQuota(Decimal("1")), quota_estimate=Decimal("5")
    )

    async def go():
        await runner.enqueue_graph(graph)
        await drain(worker)

    run(go())
    assert calls == []  # handler never called
    tts = next(r for r in ledger.rows.values() if r.passo == "tts")
    assert tts.status == "falhou" and tts.erro_codigo == "cota"
    assert progress.events[-1].message == "Falhou: Sintetizando voz (cota)"


def test_rerun_single_step_is_rodada_plus_one() -> None:
    runner, worker, ledger, progress, mover, calls, graph = build()

    async def go():
        await runner.enqueue_graph(graph)
        await drain(worker)
        calls.clear()
        nova = await runner.rerun_step(ORG, POST, 1, "render")
        await drain(worker)
        return nova

    nova = run(go())
    assert nova == 2 and calls == ["render"]  # tts/mux untouched
    r2 = ledger.rows[(ORG, POST, 2, "render")]
    assert r2.status == "concluido"
    assert ledger.rows[(ORG, POST, 1, "render")].status == "concluido"  # history kept
    assert not any(k[2] == 2 and k[3] != "render" for k in ledger.rows)


def test_bus_progress_default_impl() -> None:
    bus = FakeRealtimeBus()
    run(BusProgress(bus).publicar(ORG, POST, 1, "tts", 0.5, "Sintetizando voz (1/3)", False))


def test_graph_validation() -> None:
    with pytest.raises(ValueError):
        GraphSpec(ORG, POST, (StepSpec("a", "A", ("b",)), StepSpec("b", "B", ("a",))))
    with pytest.raises(ValueError):
        GraphSpec(ORG, POST, (StepSpec("a", "A", ("zz",)),))


def test_vendor_cost_row_shape() -> None:
    row = vendor_cost_row(org_id=ORG, step="tts", post_id=POST, vendor="elevenlabs",
                          custo_usd=Decimal("0.012"))
    assert row.category == "vendor_credits" and row.currency == "USD" and row.fx_pending
    with pytest.raises(ValueError):
        vendor_credit_usd(None, Decimal("0.0001"))


def test_worker_restart_resumes_from_job_payload() -> None:
    """A fresh runner (empty memory) claiming the persisted jobs rebuilds the graph -- inputs and
    quota estimate included -- from the payload, finishes it, and measures child-process CPU."""
    runner, worker, ledger, progress, mover, calls, graph = build(quota_estimate=Decimal("2"))
    graph = GraphSpec(ORG, POST, (
        StepSpec("tts", "Sintetizando voz", peso=2, estimativa_usd=Decimal("2"), entradas={"texto": "oi"}),
        *graph.passos[1:],
    ))
    seen: list[dict] = []

    async def go():
        await runner.enqueue_graph(graph)
        await worker.run_once()  # tts only
        # "restart": new runner + registry sharing ONLY the queue and the ledger
        reg = StepRegistry()

        async def tts(ctx):
            seen.append(ctx.entradas)
            return StepResult(saida={"audio": "a.mp3"}, vendor="fake-tts", custo_usd=Decimal("0"),
                              unidades={"caracteres": 2})

        async def render(ctx):
            return StepResult(saida={"video": "v.mp4"})

        async def mux(ctx):
            return StepResult(saida={"final": "f.mp4"})

        for n, h in (("tts", tts), ("render", render), ("mux", mux)):
            reg.register_step(n, h)
        quota = FakeQuota()
        novo = MediaGraphRunner(jobs=runner._jobs, ledger=ledger, progress=progress, quota=quota,
                                mover=mover, registry=reg, max_retries=0)
        w2 = Worker(runner._jobs, worker_id="w2", handlers=novo.handlers,
                    retry_policy=RetryPolicy(max_retries=0, backoff_seconds=0))
        await drain(w2)
        return quota

    run(go())
    assert all(r.status == "concluido" for r in ledger.rows.values())
    assert mover.movimentos[-1] == (POST, "criacao_concluida")
    assert all(r.cpu_s is not None for r in ledger.rows.values())
