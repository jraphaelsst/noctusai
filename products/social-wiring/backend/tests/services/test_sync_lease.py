"""Cross-process run lock (migration 069).

`asyncio.Lock` cannot see a second process. This can. The scheduler guard
(`NOCTUS_SCHEDULERS_ENABLED`) closed the 2026-08-22 laptop case at the
source; this is the layer underneath, for two processes that are BOTH
legitimately authorised — two containers after a replica bump.

The load-bearing assertion is the failure DIRECTION: a transport error
means "do not run". That is the opposite of the OLX drains' fail-open
pre-flight, and deliberately so — there, not running risks dropping a
real lead; here, running twice is the harm.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services import sync_lease


class _Rpc:
    def __init__(self, result, *, boom: bool = False):
        self._result = result
        self._boom = boom
        self.calls: list[tuple[str, dict]] = []

    def schema(self, _n):
        return self

    def rpc(self, name, params):
        self.calls.append((name, params))
        if self._boom:
            raise RuntimeError("postgrest unreachable")
        outer = self

        class _Call:
            def execute(self):
                return MagicMock(data=outer._result)

        return _Call()


class TestTryAcquire:
    def test_returns_a_holder_when_granted(self):
        admin = _Rpc(True)
        got = sync_lease.try_acquire(admin, "job")
        assert got is not None
        assert ":" in got, "holder should be host:pid for diagnosis"

    def test_returns_none_when_another_process_holds_it(self):
        assert sync_lease.try_acquire(_Rpc(False), "job") is None

    def test_passes_the_name_and_ttl_through(self):
        admin = _Rpc(True)
        sync_lease.try_acquire(admin, "imoveis_vista_sync", ttl_seconds=1800)
        name, params = admin.calls[0]
        assert name == "try_acquire_sync_lease"
        assert params["p_name"] == "imoveis_vista_sync"
        assert params["p_ttl_seconds"] == 1800

    def test_transport_failure_means_DO_NOT_RUN(self):
        """Fails CLOSED, unlike the OLX pre-flight.

        Skipping one nightly sync costs a day of staleness; two concurrent
        full pulls against the same catalog is the thing being prevented.
        """
        assert sync_lease.try_acquire(_Rpc(None, boom=True), "job") is None

    def test_default_ttl_is_longer_than_the_work(self):
        """The imóveis pull measures ~403s. A TTL under that would let a
        second process take the lease mid-run."""
        assert sync_lease.DEFAULT_TTL_SECONDS > 403


class TestRelease:
    def test_releases_with_the_holder_scoped(self):
        admin = _Rpc(True)
        sync_lease.release(admin, "job", "host:123")
        name, params = admin.calls[0]
        assert name == "release_sync_lease"
        assert params == {"p_name": "job", "p_holder": "host:123"}

    def test_release_failure_never_raises(self):
        """A failed release must not mask what the job just reported —
        the TTL is the real recovery path."""
        sync_lease.release(_Rpc(None, boom=True), "job", "host:123")


class TestLeaseContextManager:
    def test_yields_true_and_releases_when_granted(self):
        admin = _Rpc(True)
        with sync_lease.lease(admin, "job") as got:
            assert got is True
        assert [c[0] for c in admin.calls] == [
            "try_acquire_sync_lease", "release_sync_lease",
        ]

    def test_yields_false_and_does_NOT_release_when_denied(self):
        """Releasing a lease we never held would delete the holder's row."""
        admin = _Rpc(False)
        with sync_lease.lease(admin, "job") as got:
            assert got is False
        assert [c[0] for c in admin.calls] == ["try_acquire_sync_lease"]

    def test_releases_even_when_the_body_raises(self):
        admin = _Rpc(True)
        try:
            with sync_lease.lease(admin, "job"):
                raise ValueError("boom")
        except ValueError:
            pass
        assert "release_sync_lease" in [c[0] for c in admin.calls]


class TestObservabilityOfTheSuccessPath:
    """A safety mechanism has to be able to prove it ran.

    Until 2026-08-24 only contention and transport failure logged anything, so
    a lease that worked was indistinguishable from one that was never called —
    verifying the nightly sync in production meant reasoning backwards from
    "a fail-closed acquire would have skipped it, and it didn't skip". These
    assertions are what makes that a log line instead of an inference.
    """

    def test_a_granted_lease_says_so_with_holder_and_ttl(self, caplog):
        admin = _Rpc(True)
        with caplog.at_level("INFO"):
            sync_lease.try_acquire(admin, "job", ttl_seconds=1800, holder="box:7")
        acquired = [r for r in caplog.records if "acquired" in r.getMessage()]
        assert len(acquired) == 1
        msg = acquired[0].getMessage()
        # Holder and TTL are the two facts a stuck lease is diagnosed with.
        assert "box:7" in msg and "1800" in msg and "job" in msg

    def test_a_release_says_so_and_pairs_with_the_acquire(self, caplog):
        admin = _Rpc(True)
        with caplog.at_level("INFO"):
            with sync_lease.lease(admin, "job"):
                pass
        msgs = [r.getMessage() for r in caplog.records]
        assert sum("acquired" in m for m in msgs) == 1
        assert sum("released" in m for m in msgs) == 1

    def test_a_DENIED_lease_never_claims_to_have_acquired_one(self, caplog):
        admin = _Rpc(False)
        with caplog.at_level("INFO"):
            with sync_lease.lease(admin, "job") as got:
                assert got is False
        msgs = [r.getMessage() for r in caplog.records]
        assert not any("acquired" in m for m in msgs)
        assert not any("released" in m for m in msgs)

    def test_a_crashed_holder_leaves_an_acquire_with_no_release(self, caplog):
        """The asymmetry IS the diagnosis: it explains the later TTL takeover."""
        admin = _Rpc(True, boom=False)

        class _HalfDead(_Rpc):
            def rpc(self, name, params):
                if name == "release_sync_lease":
                    raise RuntimeError("gone")
                return super().rpc(name, params)

        admin = _HalfDead(True)
        with caplog.at_level("INFO"):
            sync_lease.release(admin, "job", sync_lease.try_acquire(admin, "job"))
        msgs = [r.getMessage() for r in caplog.records]
        assert any("acquired" in m for m in msgs)
        assert not any("released" in m for m in msgs)
