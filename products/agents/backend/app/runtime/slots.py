"""Per-conversation slot pool — contract §E.11 "Slot pool".

Seed IO shape: ``SlotPool`` Protocol + ``FakeSlotPool`` + ``RealSlotPool``
(Real) + ``get_slot_pool(settings)`` factory — the same convention as
``app.stores.approvals`` (``ApprovalStore`` / ``FakeApprovalStore`` /
``SupabaseApprovalStore`` / ``get_approval_store``).

**Why a pool at all (contract §E.11).** Every Julia turn used to run as a
single shared uid with a single shared ``HOME``, where the CLI keeps
session transcripts. A CLI compromised during one conversation's turn
could then read every OTHER conversation's transcript on the same
container. This pool leases one of ``JULIA_CLI_SLOTS`` fixed uids
(``2000+K``) per turn, and ``TurnSlot.release()`` proves the slot is
genuinely clean (no live process of that uid, no leftover handoff file)
before it goes back to the free list — the invariant the rest of §E.11's
image/wrapper/slot-script layers depend on (I1/I2/I3 in the contract).

**Seams — process scanner, killer, sweeper, clock — are ALWAYS injected**
(never monkeypatched), with a Real and a Fake implementation of each. Both
:class:`RealSlotPool` and :class:`FakeSlotPool` accept them as constructor
overrides, so a test can script an exact release scenario (a process that
survives the kill poll, a non-zero sweep, ...) regardless of which pool
flavour it starts from.

**One free list, shared release orchestration.** Discovery differs between
:class:`RealSlotPool` (validates ``JULIA_CLI_SLOTS`` fixed uids against
real ``/run/julia-K`` mounts, excluding — never silently using — a slot
whose mount is missing) and :class:`FakeSlotPool` (a plain ``capacity``
count); the release/quarantine bookkeeping itself is identical either way,
so it lives once in :class:`_BaseSlotPool`.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import time
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

__all__ = [
    "ProcessInfo",
    "ProcessScanner",
    "Killer",
    "Sweeper",
    "Clock",
    "RealProcessScanner",
    "OsKiller",
    "RealSweeper",
    "RealClock",
    "FakeProcessScanner",
    "FakeKiller",
    "FakeSweeper",
    "FakeClock",
    "TurnSlotSpec",
    "TurnSlot",
    "SlotPool",
    "RealSlotPool",
    "FakeSlotPool",
    "get_slot_pool",
]

#: Contract §E.11 — "3 slots" is the current user decision; `JULIA_CLI_SLOTS`
#: is the deploy-configurable source of truth (image `ENV JULIA_CLI_SLOTS=3`).
DEFAULT_SLOT_COUNT = 3

#: Contract §E.11 "Slot pool" step 1: "Poll for up to 5 s."
DEFAULT_KILL_POLL_SECONDS = 5.0
_DEFAULT_KILL_POLL_INTERVAL = 0.05

#: Contract §E.11 image section: "Slot users `julia-cli-K` ... for K from 0
#: to 2", uid/gid `2000+K`.
_UID_BASE = 2000


def _resolve_slot_count(settings: Any) -> int:
    """``JULIA_CLI_SLOTS`` from ``settings`` (a ``SeedSettings`` field, so
    pydantic-settings already binds the env var of the same name), falling
    back to a bare ``os.environ`` read for callers that pass a plain
    settings-shaped object without the field, and finally to
    :data:`DEFAULT_SLOT_COUNT` — mirrors
    ``app.runtime._resolve_instance_id``'s settings-then-env fallback
    shape."""
    value = getattr(settings, "julia_cli_slots", None)
    if value:
        return int(value)
    raw = os.environ.get("JULIA_CLI_SLOTS", "").strip()
    if raw:
        return int(raw)
    return DEFAULT_SLOT_COUNT


# ── Seams: process scanner ──────────────────────────────────────────────


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    uid: int
    is_zombie: bool


class ProcessScanner(Protocol):
    """Snapshot of every process currently visible to this container."""

    def scan(self) -> Sequence[ProcessInfo]: ...


class RealProcessScanner:
    """Parses ``/proc/<pid>/status`` — the real uid is the FIRST field of
    the ``Uid:`` line (real, effective, saved, fs); ``State:`` is ``Z`` for
    a zombie (contract §E.11 "Slot pool" step 1)."""

    def scan(self) -> Sequence[ProcessInfo]:
        infos: list[ProcessInfo] = []
        try:
            names = os.listdir("/proc")
        except FileNotFoundError:
            return infos
        for name in names:
            if not name.isdigit():
                continue
            try:
                with open(f"/proc/{name}/status", encoding="utf-8") as fh:
                    text = fh.read()
            except (FileNotFoundError, ProcessLookupError, PermissionError):
                continue
            uid: int | None = None
            is_zombie = False
            for line in text.splitlines():
                if line.startswith("Uid:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        uid = int(parts[1])
                elif line.startswith("State:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        is_zombie = parts[1] == "Z"
            if uid is None:
                continue
            infos.append(ProcessInfo(pid=int(name), uid=uid, is_zombie=is_zombie))
        return infos


class FakeProcessScanner:
    """Test double. ``processes`` is a plain mutable list a test scripts
    directly (add a live/zombie/other-uid entry, or let a
    :class:`FakeKiller` remove one on kill)."""

    def __init__(self, processes: Iterable[ProcessInfo] | None = None) -> None:
        self.processes: list[ProcessInfo] = list(processes or [])

    def scan(self) -> Sequence[ProcessInfo]:
        return list(self.processes)


# ── Seams: killer ────────────────────────────────────────────────────────


class Killer(Protocol):
    def kill(self, pid: int) -> None: ...


class OsKiller:
    """SIGKILL via ``os.kill`` — the CAP_KILL uvicorn keeps (contract §E.11
    I4). A process that already exited is not an error."""

    def kill(self, pid: int) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, signal.SIGKILL)


class FakeKiller:
    """Records every pid it was asked to kill. When constructed with a
    :class:`FakeProcessScanner`, it also removes the matching entry from
    that scanner's list on kill — UNLESS the pid is in ``survivors``, which
    lets a test script "this process survives the kill poll"."""

    def __init__(
        self,
        scanner: FakeProcessScanner | None = None,
        *,
        survivors: Iterable[int] = (),
    ) -> None:
        self.killed: list[int] = []
        self._scanner = scanner
        self._survivors = set(survivors)

    def kill(self, pid: int) -> None:
        self.killed.append(pid)
        if self._scanner is not None and pid not in self._survivors:
            self._scanner.processes = [p for p in self._scanner.processes if p.pid != pid]


# ── Seams: sweeper ───────────────────────────────────────────────────────


class Sweeper(Protocol):
    """Runs the slot's sweep script and returns its exit code."""

    async def sweep(self, slot: "TurnSlot") -> int: ...


class RealSweeper:
    """Spawns ``/app/bin/julia-cli-slot --julia-sweep`` as
    ``user=<slot.user_name>`` (contract §E.11 "Slot pool" step 2)."""

    def __init__(self, script_path: str = "/app/bin/julia-cli-slot") -> None:
        self._script_path = script_path

    async def sweep(self, slot: "TurnSlot") -> int:
        proc = await asyncio.create_subprocess_exec(
            self._script_path,
            "--julia-sweep",
            user=slot.user_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return await proc.wait()


class FakeSweeper:
    """Records every slot it was asked to sweep; ``exit_code`` is
    returned verbatim (non-zero scripts the "sweep failed" quarantine
    path). ``delay`` (real ``asyncio.sleep``, seconds) is a test-only knob
    for scripting "release is still in flight" — e.g. proving a shielded
    ``TurnSlot.release()`` keeps running after its awaiter is cancelled."""

    def __init__(self, exit_code: int = 0, *, delay: float = 0.0) -> None:
        self.exit_code = exit_code
        self.delay = delay
        self.calls: list["TurnSlot"] = []

    async def sweep(self, slot: "TurnSlot") -> int:
        self.calls.append(slot)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.exit_code


# ── Seams: clock ─────────────────────────────────────────────────────────


class Clock(Protocol):
    def monotonic(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class FakeClock:
    """Deterministic: ``monotonic()`` only advances when ``sleep()`` is
    awaited, so a "poll up to 5 s" test never actually waits 5 real
    seconds."""

    def __init__(self) -> None:
        self._now = 0.0

    def monotonic(self) -> float:
        return self._now

    async def sleep(self, seconds: float) -> None:
        self._now += seconds


# ── Slot data + lease ────────────────────────────────────────────────────


@dataclass(frozen=True)
class TurnSlotSpec:
    """The immutable identity of slot K — computed once at pool
    construction, independent of whether K is currently free, busy, or
    quarantined."""

    index: int
    uid: int
    user_name: str
    config_dir: str
    handoff_dir: str


class TurnSlot:
    """A leased slot (contract §E.11). Everything but ``release()`` is a
    plain read-only attribute; ``release()`` is async, shielded from
    cancellation, and idempotent — repeat calls (or a call racing a
    cancelled caller) all resolve to the SAME underlying cleanup, run
    exactly once."""

    def __init__(self, spec: TurnSlotSpec, pool: "_BaseSlotPool") -> None:
        self.index = spec.index
        self.uid = spec.uid
        self.user_name = spec.user_name
        self.config_dir = spec.config_dir
        self.handoff_dir = spec.handoff_dir
        self._pool = pool
        self._release_task: "asyncio.Task[None] | None" = None

    async def release(self) -> None:
        """Idempotent + cancellation-shielded (contract §E.11 "Slot pool").

        The first call creates the ONE cleanup task for this lease; every
        call (the first and any repeat) awaits it via ``asyncio.shield`` —
        so a caller whose own task gets cancelled mid-await still leaves
        the cleanup running to completion in the background, and a second,
        independent call to ``release()`` (e.g. a normal-completion path
        racing a timeout's ``finally``) just observes the same outcome
        instead of re-running the kill/sweep/unlink sequence.
        """
        if self._release_task is None:
            self._release_task = asyncio.ensure_future(self._pool._release(self))
        await asyncio.shield(self._release_task)


# ── Pool ─────────────────────────────────────────────────────────────────


class SlotPool(Protocol):
    def try_reserve(self) -> TurnSlot | None: ...

    async def sweep_all_on_startup(self) -> None: ...

    def health(self) -> dict[str, Any]: ...


class _BaseSlotPool:
    """Shared free-list + release orchestration for :class:`RealSlotPool`
    and :class:`FakeSlotPool`. Discovery (how the initial
    :class:`TurnSlotSpec` set and the initially-quarantined subset are
    computed) is the only thing that differs between them."""

    def __init__(
        self,
        specs: Sequence[TurnSlotSpec],
        *,
        initially_quarantined: Iterable[int] = (),
        scanner: ProcessScanner,
        killer: Killer,
        sweeper: Sweeper,
        clock: Clock,
        kill_poll_seconds: float = DEFAULT_KILL_POLL_SECONDS,
        kill_poll_interval: float = _DEFAULT_KILL_POLL_INTERVAL,
    ) -> None:
        self._specs: dict[int, TurnSlotSpec] = {s.index: s for s in specs}
        self._scanner = scanner
        self._killer = killer
        self._sweeper = sweeper
        self._clock = clock
        self._kill_poll_seconds = kill_poll_seconds
        self._kill_poll_interval = kill_poll_interval
        self._quarantined: set[int] = {
            k for k in initially_quarantined if k in self._specs
        }
        self._free: "deque[int]" = deque(
            k for k in sorted(self._specs) if k not in self._quarantined
        )
        self._busy: set[int] = set()

    # -- SlotPool protocol -------------------------------------------------

    def try_reserve(self) -> TurnSlot | None:
        """Synchronous and race-free: the check (``self._free`` non-empty)
        and the take (``popleft``) happen with no ``await`` between them —
        safe because this process runs one worker (contract §E.11 "Slot
        pool")."""
        while self._free:
            index = self._free.popleft()
            if index in self._quarantined:
                # Defensive: a slot can only reach `_quarantined` via
                # `_release`/`sweep_all_on_startup`, both of which already
                # remove it from `_free` first — this branch should be
                # unreachable, but never hand out a quarantined index.
                continue
            self._busy.add(index)
            return TurnSlot(self._specs[index], self)
        return None

    async def sweep_all_on_startup(self) -> None:
        """Runs the same kill+sweep+unlink sequence :meth:`_release` uses,
        for every NON-quarantined slot, before serving any turn (contract
        §E.11 "Every slot is swept once at startup")."""
        for index in sorted(self._specs):
            if index in self._quarantined:
                continue
            slot = TurnSlot(self._specs[index], self)
            try:
                await self._cleanup(slot)
            except Exception:
                logger.error(
                    "slot %s startup sweep failed; quarantining", index, exc_info=True
                )
                with contextlib.suppress(ValueError):
                    self._free.remove(index)
                self._quarantined.add(index)

    def health(self) -> dict[str, Any]:
        total = len(self._specs)
        quarantined = sorted(self._quarantined)
        free = len(self._free)
        busy = total - free - len(quarantined)
        return {"total": total, "free": free, "busy": busy, "quarantined": quarantined}

    # -- release orchestration, shared by TurnSlot.release() ---------------

    async def _release(self, slot: TurnSlot) -> None:
        index = slot.index
        try:
            await self._cleanup(slot)
        except Exception:
            logger.error("slot %s release failed; quarantining", index, exc_info=True)
            self._busy.discard(index)
            self._quarantined.add(index)
            return
        self._busy.discard(index)
        self._free.append(index)

    async def _cleanup(self, slot: TurnSlot) -> None:
        """Steps 1-3 of contract §E.11 "Slot pool" release. Raises on any
        failure; the caller (``_release`` / ``sweep_all_on_startup``)
        decides how to update free/busy/quarantined bookkeeping — this
        method itself never touches it."""
        await self._kill_uid_processes(slot.uid)
        exit_code = await self._sweeper.sweep(slot)
        if exit_code != 0:
            raise RuntimeError(f"slot {slot.index}: sweep exited {exit_code}")
        self._unlink_handoff(slot.handoff_dir)

    async def _kill_uid_processes(self, uid: int) -> None:
        """SIGKILL every non-zombie process with real uid ``uid``,
        including a grandchild reparented to init (the scanner walks
        every pid, not a process tree), polling for up to
        ``kill_poll_seconds``. Raises if any survive the deadline."""
        deadline = self._clock.monotonic() + self._kill_poll_seconds
        while True:
            live = [
                p for p in self._scanner.scan() if p.uid == uid and not p.is_zombie
            ]
            if not live:
                return
            for proc in live:
                self._killer.kill(proc.pid)
            if self._clock.monotonic() >= deadline:
                raise RuntimeError(
                    f"uid {uid}: {len(live)} process(es) survived the kill poll"
                )
            await self._clock.sleep(self._kill_poll_interval)

    def _unlink_handoff(self, handoff_dir: str) -> None:
        """Unlinks every entry in ``handoff_dir``. ``os.unlink`` acts on
        the directory entry itself, never the target it points at, so a
        symlink entry is removed without ever touching what it points to
        (contract §E.11: "They are uvicorn-owned; don't follow
        symlinks.")."""
        try:
            entries = list(os.scandir(handoff_dir))
        except FileNotFoundError:
            return
        for entry in entries:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(entry.path)


class RealSlotPool(_BaseSlotPool):
    """Discovers ``JULIA_CLI_SLOTS`` fixed uids against real
    ``/run/julia-K`` mounts. A slot whose mount is missing is excluded —
    quarantined from construction, never silently used — and logged."""

    def __init__(
        self,
        settings: Any,
        *,
        base_path: str = "/run",
        handoff_base_path: str | None = None,
        slot_script_path: str = "/app/bin/julia-cli-slot",
        kill_poll_seconds: float = DEFAULT_KILL_POLL_SECONDS,
    ) -> None:
        count = _resolve_slot_count(settings)
        handoff_base = handoff_base_path or os.path.join(base_path, "julia-handoff")

        specs: list[TurnSlotSpec] = []
        excluded: list[int] = []
        for k in range(count):
            mount = os.path.join(base_path, f"julia-{k}")
            specs.append(
                TurnSlotSpec(
                    index=k,
                    uid=_UID_BASE + k,
                    user_name=f"julia-cli-{k}",
                    config_dir=os.path.join(mount, "home", ".claude"),
                    handoff_dir=os.path.join(handoff_base, str(k)),
                )
            )
            if not os.path.isdir(mount):
                excluded.append(k)
                logger.error("slot %s excluded: mount %s is missing", k, mount)

        super().__init__(
            specs,
            initially_quarantined=excluded,
            scanner=RealProcessScanner(),
            killer=OsKiller(),
            sweeper=RealSweeper(slot_script_path),
            clock=RealClock(),
            kill_poll_seconds=kill_poll_seconds,
        )


class FakeSlotPool(_BaseSlotPool):
    """Dev/test :class:`SlotPool`. Takes a plain ``capacity`` — no mount
    validation, since there is no real filesystem to check. Every seam
    defaults to its Fake implementation but can be overridden to script a
    specific release scenario."""

    def __init__(
        self,
        capacity: int,
        *,
        scanner: ProcessScanner | None = None,
        killer: Killer | None = None,
        sweeper: Sweeper | None = None,
        clock: Clock | None = None,
        kill_poll_seconds: float = DEFAULT_KILL_POLL_SECONDS,
        kill_poll_interval: float = _DEFAULT_KILL_POLL_INTERVAL,
    ) -> None:
        specs = [
            TurnSlotSpec(
                index=k,
                uid=_UID_BASE + k,
                user_name=f"julia-cli-{k}",
                config_dir=f"/run/julia-{k}/home/.claude",
                handoff_dir=f"/run/julia-handoff/{k}",
            )
            for k in range(capacity)
        ]
        resolved_scanner = scanner if scanner is not None else FakeProcessScanner()
        resolved_killer = killer if killer is not None else FakeKiller(
            resolved_scanner if isinstance(resolved_scanner, FakeProcessScanner) else None
        )
        super().__init__(
            specs,
            scanner=resolved_scanner,
            killer=resolved_killer,
            sweeper=sweeper if sweeper is not None else FakeSweeper(),
            clock=clock if clock is not None else FakeClock(),
            kill_poll_seconds=kill_poll_seconds,
            kill_poll_interval=kill_poll_interval,
        )


_slot_pool_singleton: SlotPool | None = None


def get_slot_pool(settings: Any) -> SlotPool:
    """Process singleton, mirroring ``app.runtime.get_approval_broker``'s
    shape: :class:`RealSlotPool` when running for real,
    :class:`FakeSlotPool` in tests/dev — same signal every other agents
    runtime factory uses (an unconfigured ``anthropic_api_key``)."""
    global _slot_pool_singleton
    if _slot_pool_singleton is None:
        anthropic_key = getattr(settings, "anthropic_api_key", "") or ""
        if anthropic_key:
            _slot_pool_singleton = RealSlotPool(settings)
        else:
            _slot_pool_singleton = FakeSlotPool(_resolve_slot_count(settings))
    return _slot_pool_singleton
