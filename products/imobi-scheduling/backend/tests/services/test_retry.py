"""Tests for `app.services.retry` — Phase 10 retry helper.

Verifies:
  * `retry_call` succeeds first-try (no sleeps, callable invoked once).
  * Transient exceptions trigger retry up to `max_retries`; final
    failure re-raises the underlying exception.
  * Non-listed exceptions propagate immediately (no retry).
  * Sleep amounts follow the seed's `RetryPolicy` backoff formula.
  * `RETRY_POLICY_CALENDAR` + `RETRY_POLICY_WAHA` constants ship at the
    expected shape (so a one-line typo doesn't ship in prod).

Sleep is a pluggable callable — tests pass a no-op recorder so timing
is deterministic + measurable. Per the no-monkey-patching rule, we
never monkeypatch `time.sleep` globally.
"""
from __future__ import annotations

import pytest

from noctusai_lib.domain.jobs.retry_policy import RetryPolicy

from app.services.retry import (
    RETRY_POLICY_CALENDAR,
    RETRY_POLICY_WAHA,
    retry_call,
)


class _Recorder:
    """Records sleep durations + counts callable invocations."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []
        self.calls = 0

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class TestRetryCallSuccess:
    def test_first_attempt_success_no_sleeps(self):
        rec = _Recorder()

        def target():
            rec.calls += 1
            return "ok"

        result = retry_call(
            target,
            policy=RetryPolicy(max_retries=3, backoff_seconds=1.0),
            sleep=rec.sleep,
            label="test",
        )

        assert result == "ok"
        assert rec.calls == 1
        assert rec.sleeps == []

    def test_second_attempt_success_one_sleep(self):
        rec = _Recorder()
        attempts = {"n": 0}

        def target():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient")
            return "ok"

        result = retry_call(
            target,
            policy=RetryPolicy(
                max_retries=3,
                backoff_seconds=1.0,
                backoff_multiplier=2.0,
            ),
            sleep=rec.sleep,
            label="test",
        )

        assert result == "ok"
        assert attempts["n"] == 2
        # First retry uses backoff_seconds * multiplier^0 = 1.0s.
        assert len(rec.sleeps) == 1
        assert rec.sleeps[0] == pytest.approx(1.0, abs=0.001)


class TestRetryCallExhaustion:
    def test_exhausts_retries_then_raises_last_exception(self):
        rec = _Recorder()

        class _SpecificError(RuntimeError):
            pass

        attempts = {"n": 0}

        def target():
            attempts["n"] += 1
            raise _SpecificError(f"failure #{attempts['n']}")

        with pytest.raises(_SpecificError) as excinfo:
            retry_call(
                target,
                policy=RetryPolicy(
                    max_retries=2,
                    backoff_seconds=0.1,
                    backoff_multiplier=2.0,
                ),
                sleep=rec.sleep,
                label="test",
            )

        # 1 initial + 2 retries = 3 attempts.
        assert attempts["n"] == 3
        # 2 sleeps between the 3 attempts.
        assert len(rec.sleeps) == 2
        assert rec.sleeps[0] == pytest.approx(0.1, abs=0.001)
        assert rec.sleeps[1] == pytest.approx(0.2, abs=0.001)
        assert "failure #3" in str(excinfo.value)

    def test_max_retries_zero_one_shot(self):
        rec = _Recorder()
        attempts = {"n": 0}

        def target():
            attempts["n"] += 1
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError):
            retry_call(
                target,
                policy=RetryPolicy(max_retries=0),
                sleep=rec.sleep,
                label="test",
            )

        assert attempts["n"] == 1
        assert rec.sleeps == []


class TestRetryCallTransientFilter:
    def test_non_listed_exception_propagates_immediately(self):
        rec = _Recorder()
        attempts = {"n": 0}

        class _RetryableError(Exception):
            pass

        class _FatalError(Exception):
            pass

        def target():
            attempts["n"] += 1
            raise _FatalError("not retryable")

        with pytest.raises(_FatalError):
            retry_call(
                target,
                policy=RetryPolicy(max_retries=5),
                transient_exceptions=(_RetryableError,),
                sleep=rec.sleep,
                label="test",
            )

        # Fatal raised on first attempt → no retry, no sleep.
        assert attempts["n"] == 1
        assert rec.sleeps == []

    def test_listed_exception_subclass_triggers_retry(self):
        """`isinstance` semantics — a subclass of a listed exception
        also triggers retry (matches `try/except` standard behaviour)."""
        rec = _Recorder()

        class _ParentError(Exception):
            pass

        class _ChildError(_ParentError):
            pass

        attempts = {"n": 0}

        def target():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise _ChildError("retry me")
            return "ok"

        result = retry_call(
            target,
            policy=RetryPolicy(max_retries=2, backoff_seconds=0.01),
            transient_exceptions=(_ParentError,),
            sleep=rec.sleep,
            label="test",
        )

        assert result == "ok"
        assert attempts["n"] == 2


class TestBackoffCap:
    def test_backoff_capped_at_max(self):
        """`max_backoff_seconds` caps the exponential growth."""
        rec = _Recorder()
        attempts = {"n": 0}

        def target():
            attempts["n"] += 1
            if attempts["n"] < 4:
                raise RuntimeError("transient")
            return "ok"

        retry_call(
            target,
            policy=RetryPolicy(
                max_retries=5,
                backoff_seconds=10.0,
                backoff_multiplier=10.0,  # 10s, 100s, 1000s → cap at 50s
                max_backoff_seconds=50.0,
            ),
            sleep=rec.sleep,
            label="test",
        )

        # Three retries before success on the fourth attempt.
        assert len(rec.sleeps) == 3
        # 10s, 100s (capped to 50), 1000s (capped to 50).
        assert rec.sleeps[0] == pytest.approx(10.0, abs=0.01)
        assert rec.sleeps[1] == pytest.approx(50.0, abs=0.01)
        assert rec.sleeps[2] == pytest.approx(50.0, abs=0.01)


class TestPolicyConstants:
    def test_calendar_policy_shape(self):
        assert RETRY_POLICY_CALENDAR.max_retries == 3
        assert RETRY_POLICY_CALENDAR.backoff_seconds == 1.0
        assert RETRY_POLICY_CALENDAR.backoff_multiplier == 2.0
        assert RETRY_POLICY_CALENDAR.max_backoff_seconds == 30.0

    def test_waha_policy_shape(self):
        assert RETRY_POLICY_WAHA.max_retries == 3
        assert RETRY_POLICY_WAHA.backoff_seconds == 0.5
        assert RETRY_POLICY_WAHA.backoff_multiplier == 2.0
        assert RETRY_POLICY_WAHA.max_backoff_seconds == 10.0
