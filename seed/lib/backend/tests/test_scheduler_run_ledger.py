"""The seed scheduler's run instrumentation + platform timezone.

Jobs are invoked the way APScheduler invokes them — through the callable the
scheduler holds (`get_job(name).func`) — and observed through the public
`set_run_observer` seam with the seed's own `FakeRunLedger`. Nothing of ours
is patched.
"""
from __future__ import annotations

import asyncio
import logging
import threading

import pytest

from noctusai_lib.api import scheduler as sched
from noctusai_lib.domain.scheduler_runs import FakeRunLedger
from noctusai_lib.primitives import timeutil


@pytest.fixture(autouse=True)
def _reset_each_test():
    sched.reset_for_testing()
    yield
    sched.reset_for_testing()


@pytest.fixture
def ledger():
    led = FakeRunLedger("demo")
    sched.set_run_observer(led)
    return led


async def _fire(name: str):
    return await sched.scheduler.get_job(name).func()


class TestRunClassification:
    @pytest.mark.asyncio
    async def test_a_clean_run_is_ok_and_timed(self, ledger):
        async def _job():
            return {"done": 1}

        sched.register("clean", _job, hours=1)
        assert await _fire("clean") == {"done": 1}

        [run] = ledger.runs
        assert (run.job, run.status, run.error) == ("clean", "ok", None)
        assert run.finished_at >= run.started_at
        assert run.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_an_exception_is_error_and_still_propagates(self, ledger):
        async def _job():
            raise RuntimeError("upstream 502")

        sched.register("boom", _job, hours=1)
        with pytest.raises(RuntimeError):
            await _fire("boom")

        [run] = ledger.runs
        assert run.status == "error"
        assert run.error == "RuntimeError: upstream 502"

    @pytest.mark.asyncio
    async def test_skip_run_is_skipped_with_its_reason(self, ledger):
        async def _job():
            raise sched.SkipRun("switch off")

        sched.register("gated", _job, hours=1)
        assert await _fire("gated") is None
        [run] = ledger.runs
        assert (run.status, run.error) == ("skipped", "switch off")

    @pytest.mark.asyncio
    async def test_a_swallowed_failure_logged_at_error_is_still_an_error(self, ledger):
        log = logging.getLogger("demo.job")

        async def _job():
            try:
                raise ValueError("bad row")
            except ValueError as exc:
                log.error("sweep failed: %s", exc)
            return {"error": "bad row"}

        sched.register("swallower", _job, hours=1)
        await _fire("swallower")
        [run] = ledger.runs
        assert run.status == "error"
        assert run.error == "sweep failed: bad row"

    @pytest.mark.asyncio
    async def test_an_error_logged_from_a_worker_thread_counts(self, ledger):
        log = logging.getLogger("demo.thread")

        async def _job():
            await asyncio.to_thread(lambda: log.error("thread side failure"))

        sched.register("threaded", _job, hours=1)
        await _fire("threaded")
        assert ledger.runs[0].status == "error"
        assert "thread side failure" in ledger.runs[0].error

    @pytest.mark.asyncio
    async def test_warnings_do_not_fail_a_run(self, ledger):
        async def _job():
            logging.getLogger("demo").warning("slow upstream")

        sched.register("warny", _job, hours=1)
        await _fire("warny")
        assert ledger.runs[0].status == "ok"

    @pytest.mark.asyncio
    async def test_errors_logged_outside_the_run_are_not_attributed(self, ledger):
        started = asyncio.Event()
        release = asyncio.Event()

        async def _job():
            started.set()
            await release.wait()

        sched.register("innocent", _job, hours=1)
        task = asyncio.ensure_future(_fire("innocent"))
        await started.wait()
        logging.getLogger("elsewhere").error("someone else's problem")
        release.set()
        await task
        assert ledger.runs[0].status == "ok"

    @pytest.mark.asyncio
    async def test_a_sync_callable_is_supported(self, ledger):
        def _job():
            return 7

        sched.register("sync", _job, minutes=5)
        assert await _fire("sync") == 7
        assert ledger.runs[0].status == "ok"


class TestLedgerWriteIsBestEffort:
    @pytest.mark.asyncio
    async def test_a_failing_ledger_never_breaks_the_job_and_is_loud(self, caplog):
        class Broken:
            def record(self, run):
                raise ConnectionError("postgrest down")

            def register_jobs(self, specs):
                return None

        sched.set_run_observer(Broken())

        async def _job():
            return "fine"

        sched.register("resilient", _job, hours=1)
        with caplog.at_level(logging.ERROR):
            assert await _fire("resilient") == "fine"
        assert any("ledger write FAILED" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_no_observer_means_the_job_just_runs(self):
        async def _job():
            return 1

        sched.register("bare", _job, hours=1)
        assert await _fire("bare") == 1


class TestFrequentJobsDoNotWriteALedgerRowPerIdleTick:
    """A 30 s job that finds nothing must not insert 2,880 ledger rows a day (2026-11-09 egress incident:
    `POST scheduler_runs` ~10k/22h). Errors always land; clean runs are sampled to one per heartbeat."""

    @pytest.fixture
    def clock(self):
        now = {"t": 1_000.0}
        sched.set_sampling_clock(lambda: now["t"])  # the public seam; reset_for_testing() restores the real one
        return now

    @pytest.mark.asyncio
    async def test_idle_ticks_of_a_frequent_job_are_sampled(self, ledger, clock):
        async def _job():
            return None

        sched.register("fast", _job, seconds=30)
        for _ in range(240):  # 2 h of 30 s ticks
            await _fire("fast")
            clock["t"] += 30
        assert len(ledger.runs) <= 2 * 12 + 1  # one heartbeat per 5 min, never one per tick (240)

    @pytest.mark.asyncio
    async def test_errors_are_never_sampled_away_and_recovery_is_recorded(self, ledger, clock):
        state = {"fail": True}

        async def _job():
            if state["fail"]:
                raise RuntimeError("upstream 502")

        sched.register("flaky", _job, seconds=30)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await _fire("flaky")
            clock["t"] += 30
        assert [r.status for r in ledger.runs] == ["error"] * 3
        state["fail"] = False
        await _fire("flaky")  # first ok after an error: recorded at once, not at the next heartbeat
        assert ledger.runs[-1].status == "ok"

    @pytest.mark.asyncio
    async def test_a_failed_ledger_write_retries_after_a_bounded_backoff_not_every_tick(self, clock):
        class _Flaky(FakeRunLedger):
            fail = True
            attempts = 0

            def record(self, run):
                self.attempts += 1
                if self.fail:
                    raise RuntimeError("402")
                super().record(run)

        led = _Flaky("demo")
        sched.set_run_observer(led)

        async def _job():
            return None

        sched.register("fast2", _job, seconds=30)
        for _ in range(240):  # 2 h of 30 s ticks during an outage
            await _fire("fast2")
            clock["t"] += 30
        assert led.attempts <= 30  # 60s, 120s, 240s, then one per 5 min = ~26 in 2 h; never one per tick (240)
        led.fail = False
        clock["t"] += 301  # the window passes: the next tick writes (recovery is not lost)
        await _fire("fast2")
        assert len(led.runs) == 1

    @pytest.mark.asyncio
    async def test_a_job_that_is_not_frequent_records_every_run(self, ledger, clock):
        async def _job():
            return None

        sched.register("hourly", _job, hours=1)
        for _ in range(5):
            await _fire("hourly")
        assert len(ledger.runs) == 5


class TestJobRegistry:
    def test_specs_keep_the_schedule_as_written(self, monkeypatch):
        monkeypatch.delenv(timeutil.PLATFORM_TIMEZONE_ENV, raising=False)

        async def _job():
            return None

        sched.register("nightly", _job, cron="0 3 * * *", misfire_grace_time=3600)
        sched.register("every5", _job, minutes=5)
        specs = {s.job: s for s in sched.job_specs()}
        assert specs["nightly"].cron == "0 3 * * *"
        assert specs["nightly"].interval_seconds is None
        assert specs["nightly"].misfire_grace_time == 3600
        assert specs["nightly"].timezone == "America/Sao_Paulo"
        assert specs["every5"].interval_seconds == 300
        assert specs["every5"].cron is None

    def test_start_publishes_the_registry_to_the_observer(self):
        published = threading.Event()

        class Recorder(FakeRunLedger):
            def register_jobs(self, specs):
                super().register_jobs(specs)
                published.set()

        led = Recorder("demo")
        sched.set_run_observer(led)

        async def _job():
            return None

        sched.register("nightly", _job, cron="0 3 * * *")
        sched._publish_job_registry()
        assert published.wait(timeout=5)
        assert [s.job for s in led.registered] == ["nightly"]

    def test_reset_clears_specs_and_observer(self):
        async def _job():
            return None

        sched.set_run_observer(FakeRunLedger())
        sched.register("x", _job, hours=1)
        sched.reset_for_testing()
        assert sched.job_specs() == []
        assert sched.get_run_observer() is None


class TestPlatformTimezone:
    def test_default_is_sao_paulo(self, monkeypatch):
        monkeypatch.delenv(timeutil.PLATFORM_TIMEZONE_ENV, raising=False)
        assert timeutil.platform_timezone_name() == "America/Sao_Paulo"
        assert str(timeutil.platform_tz()) == "America/Sao_Paulo"

    def test_env_drives_the_cron_trigger(self, monkeypatch):
        monkeypatch.setenv(timeutil.PLATFORM_TIMEZONE_ENV, "Europe/Lisbon")

        async def _job():
            return None

        sched.register("lisbon", _job, cron="0 7 * * *")
        assert str(sched.scheduler.get_job("lisbon").trigger.timezone) == "Europe/Lisbon"
        assert sched.job_specs()[0].timezone == "Europe/Lisbon"

    def test_an_unknown_zone_fails_loudly(self, monkeypatch):
        monkeypatch.setenv(timeutil.PLATFORM_TIMEZONE_ENV, "Mars/Olympus")
        with pytest.raises(ValueError, match="NOCTUS_TIMEZONE"):
            timeutil.platform_timezone_name()
