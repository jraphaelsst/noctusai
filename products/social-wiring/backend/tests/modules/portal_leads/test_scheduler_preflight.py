"""The two OLX drains skip config resolution when there is no work.

`get_olx_config()` is deliberately never cached (`deps.py`: an operator
rotating the secret must not need a redeploy), so every call costs four
`app_integration_config` reads. Both jobs used to pay that BEFORE
checking whether the queue had anything in it.

Measured on the live project 2026-08-22: 2090 requests in 24h — 15.5% of
ALL database traffic — for two queues that have never held a single row,
on a tenant where OLX is not configured at all.

The load-bearing assertions here are the negative ones: that with an
empty queue the config provider is NOT called and the service is NOT
constructed. A test that only checked "the drain still works" would pass
against the old code and prove nothing.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from app.modules.portal_leads import scheduler as sched


class _Table:
    """Records the queries a pre-flight would issue."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.limits: list[int] = []

    def select(self, *_a, **_kw):
        return self

    def in_(self, *_a, **_kw):
        return self

    def eq(self, *_a, **_kw):
        return self

    def lte(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, n):
        self.limits.append(n)
        return self

    def execute(self):
        return MagicMock(data=self._rows[: (self.limits[-1] if self.limits else 100)])


class _Client:
    def __init__(self, rows: list[dict] | None = None):
        self.table_obj = _Table(rows or [])

    def schema(self, _n):
        return self

    def table(self, _n):
        return self.table_obj


# ─── Inbox drain (olx_leads_retry) ──────────────────────────────────────


class TestInboxDrainPreflight:
    def test_empty_queue_does_not_construct_the_service(self):
        """The service is what reads config — never build it for nothing."""
        service_factory = MagicMock()

        sched._drain_sync(
            admin_client_factory=lambda: _Client(),
            service_factory=service_factory,
            has_work_fn=lambda _c: False,
        )

        service_factory.assert_not_called()

    def test_non_empty_queue_still_drains(self):
        """The saving must not cost the actual job."""
        svc = MagicMock()
        svc.drain_pending.return_value = {"examined": 1, "processed": 1}
        service_factory = MagicMock(return_value=svc)

        sched._drain_sync(
            admin_client_factory=lambda: _Client(),
            service_factory=service_factory,
            has_work_fn=lambda _c: True,
        )

        service_factory.assert_called_once()
        svc.drain_pending.assert_called_once()

    def test_no_admin_client_skips_before_any_check(self):
        has_work = MagicMock()
        sched._drain_sync(
            admin_client_factory=lambda: None,
            service_factory=MagicMock(),
            has_work_fn=has_work,
        )
        has_work.assert_not_called()


class TestHasPendingEvents:
    def test_reports_work_when_a_row_exists(self):
        client = _Client([{"id": "abc"}])
        assert sched._has_pending_events(client) is True

    def test_reports_no_work_on_an_empty_queue(self):
        assert sched._has_pending_events(_Client([])) is False

    def test_asks_for_only_one_row(self):
        """The point is 'any work?', not fetching the batch."""
        client = _Client([{"id": "abc"}])
        sched._has_pending_events(client)
        assert client.table_obj.limits == [1]

    def test_fails_OPEN_when_the_check_errors(self):
        """"I could not tell" must run the drain, never skip it.

        Guessing "no work" on a transport blip would silently drop a real
        lead — the exact failure this module exists to prevent.
        """
        class _Boom:
            def schema(self, _n):
                return self

            def table(self, _n):
                raise RuntimeError("postgrest unreachable")

        assert sched._has_pending_events(_Boom()) is True


# ─── Forward drain (portal_lead_forward_drain) ──────────────────────────


class TestForwardDrainPreflight:
    def test_empty_outbox_does_not_call_the_drain(self):
        drain_fn = MagicMock()

        asyncio.run(
            sched._drain_forwards_async(
                admin_client_factory=lambda: _Client(),
                drain_fn=drain_fn,
                has_work_fn=lambda _c: False,
            )
        )

        drain_fn.assert_not_called()

    def test_due_forward_still_drains(self):
        async def _drain(_client, **_kw):
            _drain.called = True
            return {"examined": 1}

        _drain.called = False

        asyncio.run(
            sched._drain_forwards_async(
                admin_client_factory=lambda: _Client(),
                drain_fn=_drain,
                has_work_fn=lambda _c: True,
            )
        )

        assert _drain.called

    def test_no_admin_client_skips_before_any_check(self):
        has_work = MagicMock()
        asyncio.run(
            sched._drain_forwards_async(
                admin_client_factory=lambda: None,
                drain_fn=MagicMock(),
                has_work_fn=has_work,
            )
        )
        has_work.assert_not_called()


class TestHasDueForwards:
    def test_reports_work_when_a_row_is_due(self):
        assert sched._has_due_forwards(_Client([{"id": "f1"}])) is True

    def test_reports_no_work_on_an_empty_outbox(self):
        assert sched._has_due_forwards(_Client([])) is False

    def test_fails_OPEN_when_the_check_errors(self):
        class _Boom:
            def table(self, _n):
                raise RuntimeError("postgrest unreachable")

        assert sched._has_due_forwards(_Boom()) is True
