"""Tests for dashboard_service — delivery-status classifier + aggregation."""
from __future__ import annotations

import pytest

from app.modules.youtube.services.dashboard import DashboardService


class TestClassifyDelivery:
    """The 4-state badge: none / all_sent / partial / all_failed.

    These run on the static method so no fixture overhead.
    """

    @pytest.mark.parametrize(
        "attempts,succeeded,failed,opted_in,expected",
        [
            (0, 0, 0, False, "none"),       # opted out
            (0, 0, 0, True, "none"),        # opted in, no log rows yet
            (3, 3, 0, True, "all_sent"),    # all good
            (3, 0, 3, True, "all_failed"),  # all dispatch failed
            (3, 1, 2, True, "partial"),     # mixed
            (1, 1, 0, True, "all_sent"),    # single recipient succeeded
            (1, 0, 1, True, "all_failed"),  # single recipient failed
        ],
    )
    def test_classification(self, attempts, succeeded, failed, opted_in, expected):
        result = DashboardService._classify_delivery(
            attempts=attempts, succeeded=succeeded, failed=failed,
            opted_in=opted_in,
        )
        assert result == expected
