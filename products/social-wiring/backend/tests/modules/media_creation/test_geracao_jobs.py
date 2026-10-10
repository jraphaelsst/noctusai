"""Geração job layer: handler registry, the two workers, the fail-closed library gate."""
from __future__ import annotations

from types import SimpleNamespace

import anyio
import pytest

from noctusai_lib.domain.jobs import DeadLetterError, FakeJobRepository, JobStatus

from app.modules.media_creation.services import geracao_jobs as gj

CFG = SimpleNamespace(
    geracao_worker_enabled=True, geracao_poll_seconds=0.01, geracao_lease_seconds=30.0,
    biblioteca_poll_seconds=0.01, biblioteca_lease_seconds=30.0, biblioteca_gate_ttl_seconds=0.0,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    gj.clear_handlers()
    yield
    gj.clear_handlers()


async def _enqueue(repo, job_type, payload=None):
    return await repo.enqueue(type=job_type, payload=payload or {})


class TestRegistry:
    def test_register_get_and_idempotent_reregistration(self):
        async def h(job): ...
        gj.register_handler("headline.gerar", h)
        gj.register_handler("headline.gerar", h)
        assert gj.get_handler("headline.gerar") is h

    def test_two_different_handlers_for_a_type_is_a_wiring_bug(self):
        async def a(job): ...
        async def b(job): ...
        gj.register_handler("roteiro.gerar", a)
        with pytest.raises(gj.HandlerAlreadyRegistered):
            gj.register_handler("roteiro.gerar", b)

    def test_unknown_type_is_refused(self):
        with pytest.raises(ValueError):
            gj.register_handler("headline.typo", lambda job: None)

    def test_types_are_partitioned_between_the_two_workers(self):
        assert set(gj.GERACAO_JOB_TYPES).isdisjoint(gj.BIBLIOTECA_JOB_TYPES)
        assert set(gj.ALL_JOB_TYPES) == set(gj.GERACAO_JOB_TYPES) | set(gj.BIBLIOTECA_JOB_TYPES)


class TestGeracaoWorker:
    def test_runs_a_registered_handler_late_bound(self):
        seen: list = []

        async def handler(job):
            seen.append(job.payload["lote_id"])

        async def go():
            repo = FakeJobRepository()
            worker = gj.build_geracao_worker(repo, CFG)
            gj.register_handler("headline.gerar", handler)  # AFTER the worker was built
            await _enqueue(repo, "headline.gerar", {"lote_id": "L1"})
            assert await worker.run_once() is True
            return await repo.list_dead_letters()

        assert anyio.run(go) == [] and seen == ["L1"]

    def test_missing_handler_dead_letters_loudly(self):
        async def go():
            repo = FakeJobRepository()
            worker = gj.build_geracao_worker(repo, CFG)
            await _enqueue(repo, "roteiro.perguntas")
            await worker.run_once()
            return await repo.list_dead_letters()

        dead = anyio.run(go)
        assert len(dead) == 1 and dead[0].status == JobStatus.DEAD_LETTER

    def test_does_not_claim_library_types(self):
        async def go():
            repo = FakeJobRepository()
            worker = gj.build_geracao_worker(repo, CFG)
            await _enqueue(repo, "biblioteca.classificar")
            return await worker.run_once()

        assert anyio.run(go) is False

    def test_dead_letter_error_from_a_handler_skips_retries(self):
        async def handler(job):
            raise DeadLetterError("linha inexistente")

        gj.register_handler("roteiro.gerar", handler)

        async def go():
            repo = FakeJobRepository()
            worker = gj.build_geracao_worker(repo, CFG)
            await _enqueue(repo, "roteiro.gerar")
            await worker.run_once()
            return await repo.list_dead_letters()

        assert len(anyio.run(go)) == 1


class TestBibliotecaGate:
    def _run(self, switch):
        ran: list = []

        async def handler(job):
            ran.append(job.id)

        gj.register_handler("biblioteca.sync_perfil", handler)

        async def go():
            repo = FakeJobRepository()
            worker = gj.build_biblioteca_worker(repo, CFG, switch)
            await _enqueue(repo, "biblioteca.sync_perfil")
            return await worker.run_once()

        return anyio.run(go), ran

    def test_off_claims_nothing(self):
        claimed, ran = self._run(lambda: False)
        assert claimed is False and ran == []

    def test_on_claims_and_runs(self):
        claimed, ran = self._run(lambda: True)
        assert claimed is True and len(ran) == 1

    def test_an_unreadable_switch_is_off_fail_closed(self):
        def boom(key):
            raise RuntimeError("platform_settings unreachable")

        assert gj.read_ingestao_habilitada(boom) is False
        claimed, ran = self._run(lambda: gj.read_ingestao_habilitada(boom))
        assert claimed is False and ran == []

    @pytest.mark.parametrize("value,expected", [
        (None, False), ("", False), ("false", False), ("0", False), ("nope", False),
        ("true", True), ("1", True), ("ON", True), ("sim", True),
    ])
    def test_switch_parsing_default_off(self, value, expected):
        assert gj.read_ingestao_habilitada(lambda k: value) is expected

    def test_switch_reads_the_documented_key(self):
        keys: list = []
        gj.read_ingestao_habilitada(lambda k: keys.append(k))
        assert keys == ["biblioteca_ingestao_habilitada"]


class TestLifecycle:
    def test_geracao_disabled_does_not_start_and_submit_guard_503s(self):
        off = SimpleNamespace(**{**CFG.__dict__, "geracao_worker_enabled": False})
        assert anyio.run(lambda: gj.start_geracao_worker(off, repo=FakeJobRepository())) is False
        assert gj.is_running()["geracao"] is False
        with pytest.raises(Exception) as exc:
            gj.assert_geracao_disponivel(off)
        assert exc.value.status_code == 503 and exc.value.detail["code"] == "geracao_indisponivel"
        gj.assert_geracao_disponivel(CFG)  # on: no raise

    def test_start_and_stop_both_workers(self):
        async def go():
            repo = FakeJobRepository()
            assert await gj.start_geracao_worker(CFG, repo=repo) is True
            assert await gj.start_biblioteca_worker(CFG, repo=repo, switch=lambda: False) is True
            running = gj.is_running()
            assert await gj.start_geracao_worker(CFG, repo=repo) is True  # idempotent
            await gj.shutdown_hook()
            return running, gj.is_running()

        running, after = anyio.run(go)
        assert running == {"geracao": True, "biblioteca": True}
        assert after == {"geracao": False, "biblioteca": False}

    def test_stop_without_start_is_a_noop(self):
        anyio.run(gj.shutdown_hook)
        assert not any(gj.is_running().values())

    def test_startup_hook_isolates_a_failing_worker(self):
        calls: list = []

        async def bad():
            raise RuntimeError("adapter wiring broke")

        async def good():
            calls.append("biblioteca")

        anyio.run(gj.startup_hook, [("geracao", bad), ("biblioteca", good)])  # does not raise
        assert calls == ["biblioteca"]
