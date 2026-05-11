"""Tests for `app.services.metrics` — Phase 10 metrics-sink seam.

Verifies:
  * Default counter is `NoopCounter` (doesn't raise).
  * `configure_counter(...)` swaps the module-level counter.
  * Semantic helpers (`record_tool_dispatch`, `record_llm_call`) flow
    through the configured counter with the documented metric names +
    tag shapes.
  * `Counter` Protocol is `@runtime_checkable` — any object satisfying
    the `increment(...)` shape passes `isinstance(...)` check.
"""
from __future__ import annotations

import pytest

from app.services import metrics as metrics_mod
from app.services.metrics import (
    Counter,
    NoopCounter,
    configure_counter,
    get_counter,
    record_llm_call,
    record_tool_dispatch,
)


class _RecordingCounter:
    """Test double that records every `increment` call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, dict[str, str]]] = []

    def increment(
        self,
        metric: str,
        *,
        value: int = 1,
        tags: dict[str, str] | None = None,
    ) -> None:
        self.calls.append((metric, value, tags or {}))


@pytest.fixture(autouse=True)
def _reset_counter():
    """Reset the module-level counter back to the default Noop."""
    metrics_mod._counter = NoopCounter()
    yield
    metrics_mod._counter = NoopCounter()


class TestDefaults:
    def test_default_counter_is_noop(self):
        assert isinstance(get_counter(), NoopCounter)

    def test_noop_counter_does_not_raise(self):
        # Must accept the documented call shape without erroring.
        NoopCounter().increment("anything", value=42, tags={"a": "b"})
        NoopCounter().increment("no-tags")


class TestConfigure:
    def test_configure_swaps_counter(self):
        recorder = _RecordingCounter()
        configure_counter(recorder)
        assert get_counter() is recorder

    def test_configure_is_idempotent_across_reconfigs(self):
        first = _RecordingCounter()
        second = _RecordingCounter()
        configure_counter(first)
        configure_counter(second)
        # Last write wins.
        assert get_counter() is second


class TestSemanticHelpers:
    def test_record_tool_dispatch_emits_expected_metric(self):
        recorder = _RecordingCounter()
        configure_counter(recorder)

        record_tool_dispatch("propose_appointment", success=True)
        record_tool_dispatch("cancel_appointment", success=False)

        assert len(recorder.calls) == 2
        assert recorder.calls[0] == (
            "bot.tool_dispatch",
            1,
            {"tool": "propose_appointment", "success": "true"},
        )
        assert recorder.calls[1] == (
            "bot.tool_dispatch",
            1,
            {"tool": "cancel_appointment", "success": "false"},
        )

    def test_record_llm_call_emits_expected_metric(self):
        recorder = _RecordingCounter()
        configure_counter(recorder)

        record_llm_call(model="gpt-4o-mini", success=True)

        assert len(recorder.calls) == 1
        metric, value, tags = recorder.calls[0]
        assert metric == "bot.llm_call"
        assert value == 1
        assert tags == {"model": "gpt-4o-mini", "success": "true"}


class TestProtocolShape:
    def test_noop_satisfies_counter_protocol(self):
        # `Counter` is `@runtime_checkable` → `isinstance` works.
        assert isinstance(NoopCounter(), Counter)

    def test_recording_double_satisfies_counter_protocol(self):
        assert isinstance(_RecordingCounter(), Counter)

    def test_object_without_increment_does_not_satisfy(self):
        class _Bad:
            def something_else(self): ...

        assert not isinstance(_Bad(), Counter)
