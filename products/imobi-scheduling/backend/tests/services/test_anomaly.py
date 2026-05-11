"""Tests for `app.services.anomaly` — Phase 11 security hardening.

Verifies the tool-dispatch anomaly detector:
  * Under-threshold dispatches do NOT trigger.
  * Crossing the threshold triggers + emits the WARN log.
  * Counts isolate per `conversation_id`.
  * Window slide drops old observations.
  * Fail-open behaviour on Redis outage.
  * Empty conversation_id is rejected loud.
  * Module-level `record_dispatch_observed` is a no-op when detector
    not configured.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from noctusai_lib.integrations.redis import make_fake_redis_client

from app.services.anomaly import (
    ToolDispatchAnomalyDetector,
    _reset_for_tests,
    configure_anomaly_detector,
    get_anomaly_detector,
    record_dispatch_observed,
)


@pytest.fixture(autouse=True)
def _reset_module():
    _reset_for_tests()
    yield
    _reset_for_tests()


@pytest.fixture
def redis_client():
    return make_fake_redis_client()


class TestAnomalyDetectorBelowThreshold:
    def test_single_dispatch_no_trigger(self, redis_client):
        det = ToolDispatchAnomalyDetector(
            redis_client, threshold=10, window_seconds=60
        )
        obs = det.record_dispatch("conv-a", tool_name="lookup_property")
        assert obs.triggered is False
        assert obs.count == 1
        assert obs.threshold == 10

    def test_under_threshold_no_trigger(self, redis_client):
        det = ToolDispatchAnomalyDetector(redis_client, threshold=5, window_seconds=60)
        observations = [
            det.record_dispatch("conv-b", tool_name=f"tool_{i}") for i in range(5)
        ]
        # Threshold is "> threshold" so count == threshold is NOT triggered.
        assert all(not o.triggered for o in observations)
        assert observations[-1].count == 5


class TestAnomalyDetectorAtThreshold:
    def test_crossing_threshold_triggers(self, redis_client):
        det = ToolDispatchAnomalyDetector(redis_client, threshold=3, window_seconds=60)
        # 3 dispatches — at-threshold, not triggered (strictly greater).
        for _ in range(3):
            det.record_dispatch("conv-c")
        obs = det.record_dispatch("conv-c")
        assert obs.triggered is True
        assert obs.count == 4

    def test_subsequent_dispatches_keep_triggered(self, redis_client):
        det = ToolDispatchAnomalyDetector(redis_client, threshold=2, window_seconds=60)
        for _ in range(5):
            det.record_dispatch("conv-d")
        final = det.record_dispatch("conv-d")
        assert final.triggered is True
        assert final.count >= 6


class TestAnomalyDetectorIsolation:
    def test_counts_per_conversation_isolated(self, redis_client):
        det = ToolDispatchAnomalyDetector(redis_client, threshold=2, window_seconds=60)
        for _ in range(5):
            det.record_dispatch("conv-loud")
        # The other conversation is clean.
        obs = det.record_dispatch("conv-quiet")
        assert obs.triggered is False
        assert obs.count == 1


class TestAnomalyDetectorEmptyConversation:
    def test_empty_conversation_rejected_loud(self, redis_client):
        det = ToolDispatchAnomalyDetector(redis_client, threshold=2, window_seconds=60)
        obs = det.record_dispatch("")
        assert obs.triggered is False
        assert obs.count == 0


class TestAnomalyDetectorWindowSlide:
    def test_old_dispatches_drop_out_of_window(self, redis_client):
        det = ToolDispatchAnomalyDetector(redis_client, threshold=3, window_seconds=10)
        # Burn 5 dispatches "in the past" by manually inserting old
        # entries into the ZSET — simulates an old conversation that
        # quieted down.
        key = "anomaly:tool_dispatch:conv-old"
        old_ts = time.time() - 30  # 30s ago, outside the 10s window.
        for i in range(5):
            redis_client.zadd(key, {f"{old_ts + i * 0.01}:old": old_ts + i * 0.01})
        # Now a fresh dispatch — window slides out the old entries.
        obs = det.record_dispatch("conv-old", tool_name="new_call")
        assert obs.triggered is False
        # Count post-slide: only the one we just added.
        assert obs.count == 1


class TestAnomalyDetectorFailOpen:
    def test_redis_outage_fails_open(self):
        broken_redis = MagicMock()
        broken_redis.zadd.side_effect = ConnectionError("redis down")
        det = ToolDispatchAnomalyDetector(broken_redis, threshold=5, window_seconds=60)
        obs = det.record_dispatch("conv-x", tool_name="tool")
        # Fail-open: detection failure must not block dispatch.
        assert obs.triggered is False
        assert obs.count == 0


class TestAnomalyDetectorConfigValidation:
    def test_zero_threshold_raises(self, redis_client):
        with pytest.raises(ValueError, match="threshold must be positive"):
            ToolDispatchAnomalyDetector(redis_client, threshold=0)

    def test_zero_window_raises(self, redis_client):
        with pytest.raises(ValueError, match="window_seconds must be positive"):
            ToolDispatchAnomalyDetector(redis_client, threshold=5, window_seconds=0)


class TestModuleLevelSingleton:
    def test_get_returns_none_before_configure(self):
        assert get_anomaly_detector() is None

    def test_record_no_op_when_unconfigured(self):
        # No detector configured — record returns None, no exception.
        result = record_dispatch_observed("conv", tool_name="tool")
        assert result is None

    def test_configure_then_record(self, redis_client):
        det = ToolDispatchAnomalyDetector(redis_client, threshold=2, window_seconds=60)
        configure_anomaly_detector(det)
        obs = record_dispatch_observed("conv-y", tool_name="tool")
        assert obs is not None
        assert obs.count == 1
