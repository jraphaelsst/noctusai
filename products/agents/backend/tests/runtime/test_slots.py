"""``SlotPool`` / ``TurnSlot`` — per-conversation isolation (contract
§E.11 "Slot pool"). Seams (process scanner, killer, sweeper, clock) are
always the injected Fakes here — never a monkeypatch of this module."""
import asyncio
import os

import pytest

from app.runtime.slots import (
    FakeClock,
    FakeKiller,
    FakeProcessScanner,
    FakeSlotPool,
    FakeSweeper,
    ProcessInfo,
    RealSlotPool,
)


def _pool(capacity: int = 3, **overrides):
    return FakeSlotPool(capacity, **overrides)


class TestReserveAndRelease:
    def test_reserve_up_to_capacity_then_none(self):
        pool = _pool(2)
        first = pool.try_reserve()
        second = pool.try_reserve()
        third = pool.try_reserve()

        assert first is not None
        assert second is not None
        assert first.index != second.index
        assert third is None

    @pytest.mark.asyncio
    async def test_reserve_works_again_after_release(self):
        pool = _pool(1)
        slot = pool.try_reserve()
        assert pool.try_reserve() is None

        await slot.release()

        again = pool.try_reserve()
        assert again is not None
        assert again.index == slot.index


class TestReleaseKillsLiveProcesses:
    @pytest.mark.asyncio
    async def test_kills_every_live_process_of_that_uid_including_grandchild(self):
        scanner = FakeProcessScanner(
            [
                ProcessInfo(pid=101, uid=2000, is_zombie=False),  # direct child
                ProcessInfo(pid=102, uid=2000, is_zombie=False),  # grandchild, reparented
                ProcessInfo(pid=999, uid=1000, is_zombie=False),  # unrelated uid
            ]
        )
        killer = FakeKiller(scanner)
        pool = _pool(1, scanner=scanner, killer=killer, clock=FakeClock())
        slot = pool.try_reserve()

        await slot.release()

        assert set(killer.killed) == {101, 102}
        assert pool.health() == {"total": 1, "free": 1, "busy": 0, "quarantined": []}

    @pytest.mark.asyncio
    async def test_zombie_entries_are_ignored(self):
        scanner = FakeProcessScanner([ProcessInfo(pid=101, uid=2000, is_zombie=True)])
        killer = FakeKiller(scanner)
        pool = _pool(1, scanner=scanner, killer=killer, clock=FakeClock())
        slot = pool.try_reserve()

        await slot.release()

        assert killer.killed == []
        assert pool.health()["free"] == 1

    @pytest.mark.asyncio
    async def test_other_uid_processes_are_untouched(self):
        scanner = FakeProcessScanner([ProcessInfo(pid=555, uid=2001, is_zombie=False)])
        killer = FakeKiller(scanner)
        pool = _pool(1, scanner=scanner, killer=killer, clock=FakeClock())
        slot = pool.try_reserve()

        await slot.release()

        assert killer.killed == []
        assert [p.pid for p in scanner.processes] == [555]
        assert pool.health()["free"] == 1


class TestQuarantineOnFailure:
    @pytest.mark.asyncio
    async def test_process_surviving_the_5s_poll_quarantines_and_never_returns(self):
        scanner = FakeProcessScanner([ProcessInfo(pid=101, uid=2000, is_zombie=False)])
        # No FakeProcessScanner attachment on the killer -> killing never
        # actually removes the entry, simulating a process that survives
        # every SIGKILL attempt through the whole poll window.
        killer = FakeKiller()
        clock = FakeClock()
        pool = _pool(1, scanner=scanner, killer=killer, clock=clock)
        slot = pool.try_reserve()

        await slot.release()

        assert pool.health() == {"total": 1, "free": 0, "busy": 0, "quarantined": [0]}
        assert pool.try_reserve() is None
        # The clock actually advanced through the whole poll window (no
        # real 5 real seconds were spent — FakeClock.sleep is instant).
        assert clock.monotonic() >= 5.0

    @pytest.mark.asyncio
    async def test_nonzero_sweep_quarantines(self):
        pool = _pool(1, sweeper=FakeSweeper(exit_code=1))
        slot = pool.try_reserve()

        await slot.release()

        assert pool.health() == {"total": 1, "free": 0, "busy": 0, "quarantined": [0]}
        assert pool.try_reserve() is None

    @pytest.mark.asyncio
    async def test_sweep_all_on_startup_quarantines_a_failing_slot(self):
        pool = _pool(2, sweeper=FakeSweeper(exit_code=1))

        await pool.sweep_all_on_startup()

        assert pool.health() == {"total": 2, "free": 0, "busy": 0, "quarantined": [0, 1]}
        assert pool.try_reserve() is None


class TestHandoffUnlink:
    @pytest.mark.asyncio
    async def test_unlinks_a_symlink_without_touching_its_target(self, tmp_path):
        handoff_dir = tmp_path / "handoff" / "0"
        handoff_dir.mkdir(parents=True)
        target = tmp_path / "outside-target.jsonl"
        target.write_text("do-not-touch")
        link = handoff_dir / "session.jsonl"
        link.symlink_to(target)

        pool = _pool(1)
        # The pool builds slots with a fixed `/run/julia-handoff/K` path by
        # default; point this lease's handoff_dir at the tmp dir so the
        # unlink runs against a real filesystem.
        slot = pool.try_reserve()
        slot.handoff_dir = str(handoff_dir)

        await slot.release()

        assert not link.exists()
        assert not os.path.islink(str(link))
        assert target.exists()
        assert target.read_text() == "do-not-touch"


class TestReleaseIdempotencyAndCancellation:
    @pytest.mark.asyncio
    async def test_second_release_call_is_a_noop(self):
        sweeper = FakeSweeper()
        pool = _pool(1, sweeper=sweeper)
        slot = pool.try_reserve()

        await slot.release()
        await slot.release()

        assert len(sweeper.calls) == 1
        assert pool.health()["free"] == 1

    @pytest.mark.asyncio
    async def test_release_under_cancellation_still_completes(self):
        # A real (short) delay inside the sweep step guarantees the
        # cleanup work is GENUINELY still in flight — not already
        # resolved — at the moment we cancel the awaiting task, so this
        # actually exercises the shield rather than racing it.
        sweeper = FakeSweeper(delay=0.05)
        pool = _pool(1, sweeper=sweeper)
        slot = pool.try_reserve()

        task = asyncio.create_task(slot.release())
        await asyncio.sleep(0)  # let release() start its shielded cleanup task
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # The cleanup itself was shielded from that cancellation and keeps
        # running independently; wait for it to actually finish.
        for _ in range(200):
            if pool.health()["free"] == 1:
                break
            await asyncio.sleep(0.01)
        assert pool.health() == {"total": 1, "free": 1, "busy": 0, "quarantined": []}
        assert len(sweeper.calls) == 1


class TestHealth:
    def test_reports_exact_counts(self):
        pool = _pool(3)
        pool.try_reserve()
        pool.try_reserve()

        assert pool.health() == {"total": 3, "free": 1, "busy": 2, "quarantined": []}


class TestRealDiscovery:
    def test_excludes_a_slot_whose_mount_is_missing(self, tmp_path):
        (tmp_path / "julia-0").mkdir()
        (tmp_path / "julia-1").mkdir()
        # julia-2 deliberately NOT created.

        class _Settings:
            julia_cli_slots = 3

        pool = RealSlotPool(_Settings(), base_path=str(tmp_path))

        health = pool.health()
        assert health["total"] == 3
        assert health["quarantined"] == [2]
        assert health["free"] == 2

        reserved_indices = set()
        while True:
            slot = pool.try_reserve()
            if slot is None:
                break
            reserved_indices.add(slot.index)
        assert reserved_indices == {0, 1}
