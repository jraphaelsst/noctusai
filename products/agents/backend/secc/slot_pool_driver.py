#!/usr/bin/env python3
"""slot_pool_driver.py — piped as ``stdin`` to ``python3 -`` INSIDE the
running container, via the SAME ambient-cap ``setpriv`` bootstrap
``uvicorn_credentials_driver.py`` uses (contract §E.11, roadmap D2 SEC-C
harness checks 6/7/9).

Drives the REAL ``app.runtime.slots`` code — :class:`RealSlotPool` /
:class:`TurnSlot` — from INSIDE the real image, rather than re-implementing
the release/sweep/kill orchestration here. ``RealSweeper.sweep()``
internally does ``asyncio.create_subprocess_exec(slot_script_path,
"--julia-sweep", user=slot.user_name, ...)``, and
``_BaseSlotPool._kill_uid_processes`` does ``os.kill(pid, SIGKILL)``
across a uid boundary — BOTH need CAP_SETUID/SETGID/KILL EFFECTIVE on
THIS process, which is exactly what the entrypoint-extracted ``setpriv``
prefix (ambient, inherited across this script's own execve) provides.
This is the SAME reason ``uvicorn_credentials_driver.py`` needs that
bootstrap for a bare wrapper spawn — it is not specific to asyncio.

``settings=None`` is deliberate: :func:`app.runtime.slots._resolve_slot_
count` falls back to the bare ``JULIA_CLI_SLOTS`` env var
(``getattr(None, "julia_cli_slots", None)`` is ``None``), which the image
already sets to ``3`` — no full ``SeedSettings`` construction (and its
Supabase/JWT config requirements) is needed just to exercise the pool.

Three independent scenarios, each producing its own named result the
proof harness reports separately:
  * ``discovery`` — check 9: 3 slots discovered, a 4th reservation
    returns ``None``, releasing one and reserving again succeeds.
  * ``sweep`` — check 6: reserves slot 0 (whose tmpfs ``run_proof.py``
    seeded with junk/chmod-000/big-file leftovers AS ROOT before this
    script ran), releases it, and reports whether ``release()`` raised
    (a non-zero sweep exit would raise ``RuntimeError`` and quarantine
    the slot — caught here and reported, never left to crash the whole
    driver).
  * ``orphan`` — check 7: reserves slot 1, spawns a ``setsid``-detached
    grandchild AS that slot's uid (reparented to init, exactly the shape
    the release scan must still catch), confirms it's alive, releases the
    slot, confirms the grandchild is gone.

Stdlib only, PLUS the app package itself (already baked into the image at
``/app/products/agents/backend`` — no pip install step).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys

sys.path.insert(0, "/app/products/agents/backend")

from app.runtime.slots import RealSlotPool  # noqa: E402


async def _run_discovery() -> dict:
    pool = RealSlotPool(None)
    slots = []
    for _ in range(3):
        slot = pool.try_reserve()
        if slot is None:
            break
        slots.append(slot)
    fourth = pool.try_reserve()
    released_index = slots[0].index if slots else None
    if slots:
        await slots[0].release()
    fifth = pool.try_reserve()
    for slot in slots[1:]:
        await slot.release()
    if fifth is not None:
        await fifth.release()
    return {
        "reserved_count": len(slots),
        "reserved_indices": sorted(s.index for s in slots),
        "fourth_reservation_is_none": fourth is None,
        "released_index": released_index,
        "fifth_reservation_index": fifth.index if fifth is not None else None,
        "fifth_reservation_succeeded": fifth is not None,
    }


async def _run_sweep(seeded_slot_uid: int) -> dict:
    pool = RealSlotPool(None)
    slots = []
    target = None
    for _ in range(3):
        slot = pool.try_reserve()
        if slot is None:
            break
        slots.append(slot)
        if slot.uid == seeded_slot_uid:
            target = slot
    if target is None:
        for slot in slots:
            await slot.release()
        return {"error": f"no reserved slot has uid {seeded_slot_uid}"}
    release_error = None
    try:
        await target.release()
    except Exception as exc:  # noqa: BLE001 — surfaced verbatim, never swallowed
        release_error = f"{type(exc).__name__}: {exc}"
    health_after = pool.health()
    for slot in slots:
        if slot is not target:
            await slot.release()
    return {
        "target_uid": seeded_slot_uid,
        "target_index": target.index,
        "release_raised": release_error,
        "health_after_release": health_after,
    }


def _find_orphan_pid(uid: int) -> int | None:
    """Scans ``/proc`` for a process with real uid ``uid`` whose cmdline
    mentions both ``sleep`` and ``60`` — the DOUBLE-DETACHED grandchild
    :func:`_run_orphan` spawns below never hands its pid back directly
    (the launching shell exits immediately, orphaning it), so the release
    scan's OWN discovery mechanism (a bare ``/proc`` walk, exactly what
    :class:`~app.runtime.slots.RealProcessScanner` does) is how this
    driver finds it too. No other process in this container ever runs
    ``sleep`` — safe to match on the plain command name."""
    for entry in sorted(os.listdir("/proc")):
        if not entry.isdigit():
            continue
        pid = int(entry)
        try:
            with open(f"/proc/{pid}/status", encoding="utf-8") as fh:
                status_text = fh.read()
        except OSError:
            continue
        if not any(
            line.startswith("Uid:") and line.split()[1] == str(uid)
            for line in status_text.splitlines()
        ):
            continue
        try:
            cmdline = open(f"/proc/{pid}/cmdline", "rb").read()
        except OSError:
            continue
        if b"sleep" in cmdline and b"60" in cmdline:
            return pid
    return None


async def _run_orphan() -> dict:
    """Contract §E.11 D2 check 7: a ``setsid``-detached GRANDCHILD
    (reparented to init, not a direct child of this driver) must still be
    caught and killed by ``TurnSlot.release()``'s ``/proc`` scan before
    the slot returns to the free list. The launching shell backgrounds
    ``sleep`` via ``setsid`` (new session, no controlling terminal) then
    exits immediately (``disown`` + the shell's own exit) — at that point
    ``sleep`` has NO living parent of its own and the kernel reparents it
    to PID 1, exactly the shape the contract calls out."""
    pool = RealSlotPool(None)
    slots = []
    target = None
    for _ in range(3):
        slot = pool.try_reserve()
        if slot is None:
            break
        slots.append(slot)
        if target is None:
            target = slot
    if target is None:
        return {"error": "no slot available to reserve"}

    launcher = await asyncio.create_subprocess_exec(
        "/bin/sh",
        "-c",
        "setsid sleep 60 </dev/null >/dev/null 2>&1 &",
        user=target.user_name,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await launcher.wait()  # the launching shell exits almost immediately
    await asyncio.sleep(0.3)  # let the kernel finish the setsid + reparent
    orphan_pid = _find_orphan_pid(target.uid)
    alive_before = orphan_pid is not None and _still_alive(orphan_pid)

    release_error = None
    try:
        await target.release()
    except Exception as exc:  # noqa: BLE001 — surfaced verbatim
        release_error = f"{type(exc).__name__}: {exc}"

    await asyncio.sleep(0.2)
    alive_after = orphan_pid is not None and _still_alive(orphan_pid)
    still_findable_after = _find_orphan_pid(target.uid) is not None

    # Best-effort cleanup if the release scan somehow missed it (the
    # assertion above is what actually FAILS the check; this is just
    # hygiene for this driver's own run).
    if orphan_pid is not None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(orphan_pid, 9)

    for slot in slots:
        if slot is not target:
            await slot.release()

    return {
        "target_uid": target.uid,
        "target_index": target.index,
        "orphan_pid": orphan_pid,
        "orphan_alive_before_release": alive_before,
        "orphan_alive_after_release": alive_after,
        "orphan_still_findable_after_release": still_findable_after,
        "release_raised": release_error,
    }


def _still_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def _main_async() -> dict:
    result: dict = {"driver_uid": os.getuid()}
    result["discovery"] = await _run_discovery()
    result["sweep"] = await _run_sweep(seeded_slot_uid=2000)
    result["orphan"] = await _run_orphan()
    return result


def main() -> int:
    result = asyncio.run(_main_async())
    print(f"SECC_POOL_DRIVER_JSON:{json.dumps(result)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
