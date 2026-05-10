"""Unit tests for `noctusai_lib.primitives.tasks`.

Covers:
- schedule-and-run-to-completion
- returned-Task contract for caller tracking
- exception logging via supplied logger (`logger.error` with exc_info)
- exception logging via module-level fallback logger
- cancellation logged at debug, NOT exception
- no-running-loop raises typed `NoRunningLoopError`
- optional `name` propagates to the Task

The `# silent-ok` retirement (memory `feedback_silent_ok_is_not_a_substitute_for_logging`)
makes "exception eaten silently" a regression class. The exception-logging
tests are the regression detector for that.
"""
from __future__ import annotations

import asyncio
import logging

import pytest

from noctusai_lib.primitives.tasks import NoRunningLoopError, schedule_coro


def _run(coro):
    """Run a coroutine on a fresh event loop, returning its result.

    Mirrors the pattern in `test_jobs.py` so seed tests stay consistent
    even though `pytest-asyncio` is available.
    """
    return asyncio.run(coro)


class TestScheduleCoro:
    def test_schedules_and_runs_to_completion(self):
        """Bare schedule path: task runs, no exception, success path."""
        results: list[int] = []

        async def work() -> None:
            await asyncio.sleep(0)
            results.append(42)

        async def driver() -> None:
            task = schedule_coro(work())
            await task

        _run(driver())
        assert results == [42]

    def test_returns_task_for_caller_tracking(self):
        """Returned object is a Task that callers can store / await /
        cancel — matches the certidoes_service per-org idempotency
        pattern (`_tjsp_scheduled_tasks[org_id] = task`)."""

        async def work() -> str:
            return "ok"

        async def driver() -> "asyncio.Task[str]":
            task = schedule_coro(work())
            assert isinstance(task, asyncio.Task)
            return task

        task = _run(driver())
        # Task survives the loop close — but only after completion.
        # asyncio.run closes the loop AFTER all tasks finish; so by
        # this point the task is done.
        assert task.done()
        assert task.result() == "ok"

    def test_logs_exception_via_supplied_logger(self, caplog):
        """If the wrapped coroutine raises, the supplied logger logs
        the exception with traceback — never silent."""
        custom_logger = logging.getLogger("noctusai_lib.tests.tasks.custom")

        async def boom() -> None:
            raise ValueError("kapow")

        async def driver() -> None:
            task = schedule_coro(boom(), logger=custom_logger, name="boom_task")
            # Drain so the done_callback runs while the loop is alive.
            try:
                await task
            except ValueError:
                pass

        with caplog.at_level(logging.ERROR, logger="noctusai_lib.tests.tasks.custom"):
            _run(driver())

        # The error log carries the task name + the exception traceback.
        error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
        assert any("boom_task" in r.getMessage() for r in error_records), (
            f"expected 'boom_task' in error log; got {[r.getMessage() for r in error_records]}"
        )
        # Traceback is attached via exc_info.
        assert any(r.exc_info is not None for r in error_records), (
            "expected at least one ERROR record to carry exc_info (the traceback)"
        )

    def test_logs_exception_via_module_logger_when_no_logger_supplied(self, caplog):
        """No `logger` arg → falls back to the module logger.
        Exception still logged; never silent."""

        async def boom() -> None:
            raise RuntimeError("module-fallback-boom")

        async def driver() -> None:
            task = schedule_coro(boom(), name="fallback_task")
            try:
                await task
            except RuntimeError:
                pass

        with caplog.at_level(logging.ERROR, logger="noctusai_lib.primitives.tasks"):
            _run(driver())

        error_records = [
            r for r in caplog.records
            if r.levelno == logging.ERROR and r.name == "noctusai_lib.primitives.tasks"
        ]
        assert error_records, "expected module logger to record the exception"
        assert any("fallback_task" in r.getMessage() for r in error_records)

    def test_cancelled_error_logged_at_debug_not_error(self, caplog):
        """A cancelled task logs at DEBUG, not ERROR — shutdown-time
        cancels shouldn't pollute prod logs with stack traces."""
        custom_logger = logging.getLogger("noctusai_lib.tests.tasks.cancel")

        async def slow() -> None:
            await asyncio.sleep(10)

        async def driver() -> None:
            task = schedule_coro(slow(), logger=custom_logger, name="cancel_task")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        with caplog.at_level(logging.DEBUG, logger="noctusai_lib.tests.tasks.cancel"):
            _run(driver())

        # ERROR records for this logger: NONE (cancel is not an error).
        error_records = [
            r for r in caplog.records
            if r.levelno == logging.ERROR and r.name == "noctusai_lib.tests.tasks.cancel"
        ]
        assert not error_records, (
            f"cancel should not produce ERROR records; got {[r.getMessage() for r in error_records]}"
        )
        # DEBUG record carries the task name.
        debug_records = [
            r for r in caplog.records
            if r.levelno == logging.DEBUG and r.name == "noctusai_lib.tests.tasks.cancel"
        ]
        assert any("cancel_task" in r.getMessage() for r in debug_records), (
            f"expected 'cancel_task' in debug log; got {[r.getMessage() for r in debug_records]}"
        )

    def test_no_running_loop_raises_typed_error(self):
        """Calling outside a running loop raises NoRunningLoopError
        (a typed RuntimeError subclass) — never a bare RuntimeError
        whose message reads 'no running event loop'."""

        async def work() -> None:
            pass

        # Build the coroutine outside any running loop — schedule_coro
        # itself is a sync function and is called here from a sync
        # context.
        coro = work()
        try:
            with pytest.raises(NoRunningLoopError) as exc_info:
                schedule_coro(coro, name="no_loop")
            # Message names the helper + includes the task name.
            assert "schedule_coro" in str(exc_info.value)
            assert "no_loop" in str(exc_info.value)
            # Subclass relationship: NoRunningLoopError IS a RuntimeError.
            assert isinstance(exc_info.value, RuntimeError)
        finally:
            # The bare coroutine was never awaited; suppress the
            # RuntimeWarning. schedule_coro already closed it via
            # `coro.close()` before raising, so this is just defensive.
            try:
                coro.close()
            except RuntimeError:
                pass

    def test_optional_name_propagates_to_task(self):
        """`name=` flows through to `Task.get_name()` so loop dumps
        and the done-callback log line stay distinguishable."""

        async def work() -> None:
            pass

        captured: dict[str, str] = {}

        async def driver() -> None:
            task = schedule_coro(work(), name="my_named_task")
            captured["name"] = task.get_name()
            await task

        _run(driver())
        assert captured["name"] == "my_named_task"

    def test_omitted_name_keeps_default_task_name(self):
        """No `name=` arg → asyncio's default Task naming applies
        (something like 'Task-N'). Helper does not force a name."""

        async def work() -> None:
            pass

        captured: dict[str, str] = {}

        async def driver() -> None:
            task = schedule_coro(work())
            captured["name"] = task.get_name()
            await task

        _run(driver())
        # Default-named tasks start with 'Task-' in CPython's asyncio.
        assert captured["name"].startswith("Task-"), (
            f"expected default 'Task-N' name; got {captured['name']!r}"
        )
