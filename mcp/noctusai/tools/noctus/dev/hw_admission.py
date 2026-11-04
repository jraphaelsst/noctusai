"""noctus.dev.hw_admission — machine-wide hardware admission gate for heavy runs.

WHY (2026-11-04): an 8-core / 8 GB laptop shared by many Claude sessions. Two
heavy suites overlapping starved each other (RG integrate: 40 vitest timeouts in
untouched tests + an e2e page.goto timeout at load 52) -> false-reds, and the
box paged 5+ GB of swap. Every heavy run that ran ALONE was green. The owner
asked for a safety gate that preserves the hardware, pushes it to its MEASURED
capacity, and is re-tunable per machine ("dinamicizable").

WHAT IS HEAVY: product pytest suites, vitest, playwright/e2e, vite build, every
gate_sweep leg and task_branch merged-tip gate. Light (no slot): git, single
tests, keepers, MCP reads.

MECHANISM
- Budget: ``deploy/fleet/hardware-budget.json`` keyed by PHASE, with per-HOST
  overrides (``hosts[<hostname>]``) so each machine carries its own profile.
  Phase resolution: env ``NOCTUS_HW_PHASE`` > ``hosts[host].phase`` > ``phase``.
- Slots: ``max_heavy`` lock files under ``~/.noctus/hw-slots`` (``fcntl.flock``),
  machine-wide across sessions and worktrees; the OS frees a slot when its
  holder dies, so a crash never wedges the box. A child process inherits its
  parent's slot via ``NOCTUS_HW_SLOT_HELD`` (no self-deadlock when task_branch
  shells out to a gate).
- Probe (NOT load average — on macOS it counts I/O/memory-blocked threads and
  decays slowly; measured load 21-29 at 89% CPU idle): CPU idle over a window,
  free+reclaimable memory, swap-out rate. All three must pass to admit.
- No silent start: on timeout the verdict is ``waiting_for_slot`` and the job
  is NOT run; the caller reports it as not-run/inconclusive, never a pass/fail.
- Capacity log: every admission + run lands in ``~/.noctus/hw-admission.ndjson``
  (machine-local by design: capacity is a property of THIS machine); ``report``
  summarizes it so later phases are set from data, not guesses.

KB § PATTERNS/devops/hardware-admission-budget.md
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import platform
import re
import resource
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

# The budget path resolves LAZILY: the module also runs as a standalone copy
# (the out-of-repo sampler), where there is no repo root above it.
_BUDGET_REL = Path("deploy") / "fleet" / "hardware-budget.json"


def _default_budget() -> Path:
    here = Path(__file__).resolve()
    root = here.parents[5] if len(here.parents) > 5 else None
    if root is not None and (root / "mcp" / "noctusai").is_dir():
        return root / _BUDGET_REL
    raise BudgetError(f"{here} is outside the repo - set NOCTUS_HW_BUDGET_PATH")
_HELD_ENV = "NOCTUS_HW_SLOT_HELD"
_REQUIRED_KNOBS = ("max_heavy", "min_cpu_idle_pct", "cpu_sample_s",
                   "min_reclaimable_mb", "max_swapout_per_s", "wait_s", "poll_s")


class BudgetError(RuntimeError):
    """The budget file is missing / malformed / names an unknown phase."""


# ── budget ────────────────────────────────────────────────────────────────

def _host() -> str:
    return socket.gethostname().split(".")[0].lower()


def _aborts_path() -> Path:
    p = Path(os.environ.get("NOCTUS_HW_ABORTS") or Path.home() / ".noctus" / "hw-trial-aborts.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_aborts() -> dict[str, str]:
    p = _aborts_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise BudgetError(f"trial-abort marker is not valid JSON: {p}: {exc}") from exc


def _iso(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def _abort_key(entry: dict[str, Any]) -> str:
    return f"{entry['phase']}@{entry['from']}"


def active_schedule_entry(doc: dict[str, Any], host: str, now: float) -> dict[str, Any] | None:
    """The `schedule` entry covering `now` for this host, unless that trial was
    aborted after it started (an abort sends the machine back to its normal
    phase for the rest of that entry's window)."""
    aborts = _read_aborts()
    for e in doc.get("schedule") or []:
        hosts = e.get("hosts")
        if hosts and host not in [h.lower() for h in hosts]:
            continue
        if _iso(e["from"]) <= now < _iso(e["until"]):
            # An abort is keyed to THIS window (phase + from), not to a clock
            # comparison, so it can never be silently ignored by skew.
            if _abort_key(e) in aborts:
                return None
            return e
    return None


def load_budget(path: Path | None = None, phase: str | None = None,
                host: str | None = None, now: float | None = None) -> dict[str, Any]:
    """Resolve the effective budget for this host. Raises BudgetError — a
    missing budget is a setup error, never a silent 'no gate'.

    Phase precedence: explicit `phase` > env NOCTUS_HW_PHASE > the active
    `schedule` entry (a time-boxed, machine-wide trial) > hosts[host].phase >
    top-level `phase`."""
    env_path = os.environ.get("NOCTUS_HW_BUDGET_PATH")
    p = Path(env_path) if env_path else (Path(path) if path else _default_budget())
    try:
        doc = json.loads(p.read_text())
    except FileNotFoundError as exc:
        raise BudgetError(f"hardware budget not found: {p}") from exc
    except json.JSONDecodeError as exc:
        raise BudgetError(f"hardware budget is not valid JSON: {p}: {exc}") from exc
    host = (host or _host()).lower()
    host_cfg = (doc.get("hosts") or {}).get(host, {})
    entry = active_schedule_entry(doc, host, now if now is not None else time.time())
    chosen = (phase or os.environ.get("NOCTUS_HW_PHASE") or (entry or {}).get("phase")
              or host_cfg.get("phase") or doc.get("phase"))
    phases = doc.get("phases") or {}
    if chosen not in phases:
        raise BudgetError(f"phase {chosen!r} not in {sorted(phases)} ({p})")
    eff = {**phases[chosen], **(host_cfg.get("overrides") or {})}
    missing = [k for k in _REQUIRED_KNOBS if k not in eff]
    if missing:
        raise BudgetError(f"phase {chosen!r} lacks knob(s) {missing} ({p})")
    eff.update(phase=chosen, host=host, budget_path=str(p),
               trial=({"phase": entry["phase"], "from": entry["from"], "until": entry["until"],
                       "abort": entry.get("abort")} if entry and chosen == entry["phase"] else None))
    return eff


def _check_trial_abort(budget: dict[str, Any], metrics: dict[str, Any],
                       busy_slots: int | None = None) -> dict[str, Any] | None:
    """Abort the active trial when the last `consecutive` samples of it (this
    one included) all breach its abort limits. Writes the marker + returns
    the abort record (None = no abort).

    Only GATED samples count (owner, 2026-11-04): trial-mh2-mem aborted at
    17:57Z partly on a sample with ZERO slots held that still swapped at
    3023 pages/s - Chrome and ungated sessions, load the gate never admitted.
    A sample with no slot held neither counts nor breaks the streak; admission
    itself still refuses new work on a swapping machine. `busy_slots` None
    (unknown) counts. Opt back into machine-wide counting with
    `"count_ungated": true` in the abort rule."""
    trial = budget.get("trial") or {}
    rule = trial.get("abort") or {}
    if not rule or "probe_error" in metrics:
        return None
    gated_only = not rule.get("count_ungated", False)
    if gated_only and busy_slots == 0:
        return None

    def breach(m: dict[str, Any]) -> bool:
        return (m.get("reclaimable_mb", 1e12) < rule.get("reclaimable_mb_below", -1)
                or m.get("swapout_per_s", 0) >= rule.get("swapout_at_least", 1e12))

    n = int(rule.get("consecutive", 3))
    p = _log_path()
    prior = [json.loads(ln) for ln in p.read_text().splitlines()[-400:] if ln.strip()] if p.exists() else []
    prior = [r for r in prior if r.get("event") == "sample" and r.get("phase") == trial["phase"]
             and not (gated_only and r.get("busy_slots") == 0)][-(n - 1):] if n > 1 else []
    window = [r.get("metrics", {}) for r in prior] + [metrics]
    if len(window) < n or not all(breach(m) for m in window):
        return None
    aborts = _read_aborts()
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    aborts[_abort_key(trial)] = at
    # A stepped experiment never climbs past a failed step. 2026-11-04:
    # trial-mh2 aborted on swap, and trial-mh3 (chained right after it) had to
    # be cancelled by hand. Every later step chained to this one (its `from` ==
    # the previous step's `until`) is cancelled with it, by construction.
    cancelled = _chained_later_steps(budget, trial)
    for e in cancelled:
        aborts[_abort_key(e)] = at
    _aborts_path().write_text(json.dumps(aborts, indent=2))
    rec = {"phase": trial["phase"], "window_from": trial["from"], "rule": rule, "metrics": metrics,
           "at": at, "cancelled_steps": [_abort_key(e) for e in cancelled]}
    _log({"event": "trial_aborted", "host": budget["host"], **rec})
    return rec


def _chained_later_steps(budget: dict[str, Any], trial: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        doc = json.loads(Path(budget["budget_path"]).read_text())
    except (KeyError, OSError, json.JSONDecodeError):
        return []
    host = budget.get("host", "")
    steps = sorted((e for e in doc.get("schedule") or []
                    if not e.get("hosts") or host in [h.lower() for h in e["hosts"]]),
                   key=lambda e: _iso(e["from"]))
    out, until = [], _iso(trial["until"])
    for e in steps:
        if _iso(e["from"]) == until:
            out.append(e)
            until = _iso(e["until"])
    return out


# ── probe ─────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: float = 30) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True).stdout


def _darwin_vm() -> dict[str, int]:
    out = _run(["vm_stat"])
    page = int(re.search(r"page size of (\d+)", out).group(1))
    vals = {m.group(1).strip(): int(m.group(2))
            for m in re.finditer(r"^([^:\n]+):\s+(\d+)\.?$", out, re.M)}
    vals["_page"] = page
    return vals


def _linux_meminfo() -> dict[str, int]:
    vals: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        vals[k] = int(v.split()[0]) * 1024
    return vals


def _linux_pswpout() -> int:
    for line in Path("/proc/vmstat").read_text().splitlines():
        if line.startswith("pswpout "):
            return int(line.split()[1])
    return 0


def _linux_cpu() -> tuple[int, int]:
    f = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    return f[3] + (f[4] if len(f) > 4 else 0), sum(f)


def _claude_sessions() -> int:
    out = _run(["ps", "-Ao", "comm="])
    return sum(1 for ln in out.splitlines() if ln.strip().rsplit("/", 1)[-1] == "claude")


def probe(sample_s: float = 10.0) -> dict[str, Any]:
    """Sample CPU idle, reclaimable memory and swap-out over `sample_s`.

    ``swapout_per_s`` is PAGES per second over the MEASURED interval between
    the two counter reads (never the nominal ``sample_s`` — under load the
    interval stretches and dividing by the nominal value inflated the rate
    ~10x); ``swapout_mb_per_s`` is the same rate in MB. ``elapsed_s`` is the
    measured interval. Errors are returned as ``probe_error`` (caller treats
    as NOT admitted)."""
    sample_s = max(1.0, float(sample_s))
    system = platform.system()
    try:
        if system == "Darwin":
            v0, t0 = _darwin_vm(), time.monotonic()
            top = _run(["top", "-l", "2", "-s", str(int(sample_s)), "-n", "0"], timeout=sample_s + 30)
            v1, t1 = _darwin_vm(), time.monotonic()
            idles = re.findall(r"CPU usage:.*?([\d.]+)% idle", top)
            cpu_idle = float(idles[-1])
            pg = v1["_page"]
            reclaim = sum(v1.get(k, 0) for k in
                          ("Pages free", "Pages inactive", "Pages purgeable", "Pages speculative")) * pg
            swap_pages = v1.get("Swapouts", 0) - v0.get("Swapouts", 0)
        elif system == "Linux":
            s0, c0, t0 = _linux_pswpout(), _linux_cpu(), time.monotonic()
            time.sleep(sample_s)
            s1, c1, t1 = _linux_pswpout(), _linux_cpu(), time.monotonic()
            pg = os.sysconf("SC_PAGE_SIZE")
            cpu_idle = 100.0 * (c1[0] - c0[0]) / max(1, c1[1] - c0[1])
            reclaim = _linux_meminfo().get("MemAvailable", 0)
            swap_pages = s1 - s0
        else:
            return {"probe_error": f"unsupported platform {system}"}
        elapsed = max(t1 - t0, 1e-3)
        swapout = swap_pages / elapsed
        sessions = _claude_sessions()
    except (subprocess.SubprocessError, OSError, AttributeError, IndexError, ValueError) as exc:
        return {"probe_error": f"{type(exc).__name__}: {exc}"}
    return {"cpu_idle_pct": round(cpu_idle, 1), "reclaimable_mb": round(reclaim / 2**20),
            "swapout_per_s": round(swapout, 1),
            "swapout_mb_per_s": round(swapout * pg / 2**20, 2), "claude_sessions": sessions,
            "load_1m": round(os.getloadavg()[0], 2), "cpu_cores": os.cpu_count(),
            "sample_s": sample_s, "elapsed_s": round(elapsed, 2)}


def job_workers(budget: dict[str, Any] | None = None) -> int:
    """Internal worker cap for ONE heavy job (vitest --maxWorkers, playwright
    --workers). The slot count bounds how many jobs run; this bounds how wide
    each one fans out. 2026-11-04: with a single slot, one vitest run still
    started ~7 workers on the 8-core M2 and pushed it into swap. The budget's
    ``job_workers`` wins; when absent it is cores / (2 x max_heavy), never < 1.
    An unreadable budget gives 1: the conservative answer, never "uncapped"."""
    try:
        b = budget or load_budget()
    except BudgetError:
        return 1
    v = b.get("job_workers")
    if v is None:
        v = (os.cpu_count() or 2) // (2 * max(1, int(b.get("max_heavy") or 1)))
    return max(1, int(v))


_FANOUT_KINDS = frozenset({"vitest", "e2e", "playwright"})
_AUTO = object()


def fanout_cap(job: str, budget: dict[str, Any] | None = None) -> int | None:
    """The worker cap a job of this NAME runs with, or None for a job with no
    fan-out (pytest, vite build, keepers). Job names are `kind:target`, and
    gate jobs `gate:kind:target`, so any `vitest` / `e2e` / `playwright`
    segment marks a capped job: the same commands cap_worker_argv caps."""
    return job_workers(budget) if _FANOUT_KINDS & set(job.split(":")) else None


def _job_kind(job: str) -> str:
    """`gate:pytest:social-wiring` -> `gate:pytest`; `predeploy:core` -> `predeploy`."""
    parts = job.split(":")
    return ":".join(parts[:-1]) if len(parts) > 1 else job


def expected_peak_mb(job: str, rows: list[dict[str, Any]] | None = None,
                     default: float = 1024.0) -> tuple[float, str]:
    """p90 of this job's measured `children_peak_rss_mb` (nearest rank), else
    its kind's, else `default`; with the source used. CAVEAT: the measure is
    the largest single reaped child (ru_maxrss), so a multi-process job
    (vitest workers) is UNDER-counted. Treat it as a floor, which is why the
    default stays conservative."""
    if rows is None:
        p = _log_path()
        rows = [json.loads(ln) for ln in p.read_text().splitlines()[-5000:] if ln.strip()] \
            if p.exists() else []
    ran = [r for r in rows if r.get("event") == "ran" and r.get("children_peak_rss_mb")]

    def p90(vals: list[float]) -> float:
        v = sorted(vals)
        return float(v[max(0, -(-9 * len(v) // 10) - 1)])

    exact = [r["children_peak_rss_mb"] for r in ran if r.get("job") == job]
    if exact:
        return p90(exact), "job"
    kind = _job_kind(job)
    same = [r["children_peak_rss_mb"] for r in ran if _job_kind(str(r.get("job", ""))) == kind]
    if same:
        return p90(same), "kind"
    return float(default), "default"


def memory_veto(job: str, metrics: dict[str, Any], budget: dict[str, Any], others: int,
                rows: list[dict[str, Any]] | None = None) -> list[str]:
    """Memory-aware admission for a heavy job joining `others` running ones.
    trial-mh2 (2026-11-04): a slot count of 2 let two full suites in together
    and swapped the 8 GB M2. The slot count is now a ceiling; memory decides.
    The first heavy job is judged by the plain thresholds alone."""
    if others < 1:
        return []
    peak, src = expected_peak_mb(job, rows, budget.get("default_job_peak_mb", 1024))
    left = metrics.get("reclaimable_mb", 0) - peak
    if left >= budget["min_reclaimable_mb"]:
        return []
    return [f"memory: reclaimable {metrics.get('reclaimable_mb')} MB - expected peak {peak:.0f} MB "
            f"({src}) = {left:.0f} MB < {budget['min_reclaimable_mb']} MB with {others} heavy "
            "job(s) already running"]


def cap_worker_argv(argv: list[str], workers: int) -> list[str]:
    """Add the worker cap to a known fan-out command; anything else (and any
    command that already sets its own cap) is returned unchanged."""
    a = list(argv)
    if a[:2] == ["npm", "test"] and not any(x.startswith("--maxWorkers") for x in a):
        return a + (["--"] if "--" not in a else []) + [f"--maxWorkers={workers}"]
    if a[:3] == ["npx", "playwright", "test"] and not any(
            x.startswith("--workers") or x == "-j" for x in a):
        return a + [f"--workers={workers}"]
    return a


def evaluate(metrics: dict[str, Any], budget: dict[str, Any]) -> list[str]:
    """Return the list of failed admission conditions (empty = admit)."""
    if "probe_error" in metrics:
        return [f"probe_error: {metrics['probe_error']}"]
    why = []
    if metrics["cpu_idle_pct"] < budget["min_cpu_idle_pct"]:
        why.append(f"cpu_idle {metrics['cpu_idle_pct']}% < {budget['min_cpu_idle_pct']}%")
    if metrics["reclaimable_mb"] < budget["min_reclaimable_mb"]:
        why.append(f"reclaimable {metrics['reclaimable_mb']}MB < {budget['min_reclaimable_mb']}MB")
    if metrics["swapout_per_s"] >= budget["max_swapout_per_s"]:
        why.append(f"swapout {metrics['swapout_per_s']}/s >= {budget['max_swapout_per_s']}/s")
    return why


def advisories(metrics: dict[str, Any], budget: dict[str, Any]) -> list[str]:
    cap = budget.get("max_claude_sessions_advisory")
    n = metrics.get("claude_sessions")
    if cap is not None and n is not None and n > cap:
        return [f"{n} claude processes running (advisory cap {cap}) - close idle sessions"]
    return []


# ── slots ─────────────────────────────────────────────────────────────────

def _slot_dir() -> Path:
    d = Path(os.environ.get("NOCTUS_HW_SLOT_DIR") or Path.home() / ".noctus" / "hw-slots")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log_path() -> Path:
    p = Path(os.environ.get("NOCTUS_HW_LOG") or Path.home() / ".noctus" / "hw-admission.ndjson")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# Bumped whenever a probe metric changes meaning, so consumers (usage_eval's
# dev_telemetry sync) can tell old rows from corrected ones.
# 1 = swap rate divided by the NOMINAL sample_s (inflated under load: top's
#     startup + spawns can take far longer than sample_s) — an upper bound.
# 2 = swap rate divided by the measured wall-clock interval; + swapout_mb_per_s.
PROBE_VERSION = 2


def _log(row: dict[str, Any]) -> None:
    row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "probe_version": PROBE_VERSION, **row}
    with _log_path().open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def holders() -> list[dict[str, Any]]:
    """Who holds each slot right now (a slot is held iff its flock is taken)."""
    out = []
    for f in sorted(_slot_dir().glob("slot-*.lock")):
        with f.open("a+") as fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fh.seek(0)
                try:
                    info = json.loads(fh.read() or "{}")
                except json.JSONDecodeError:
                    info = {}
                out.append({"slot": f.name, **info})
            else:
                fcntl.flock(fh, fcntl.LOCK_UN)
    return out


def _try_slot(n: int, job: str) -> tuple[Any, Path] | None:
    for i in range(n):
        f = _slot_dir() / f"slot-{i}.lock"
        fh = f.open("a+")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            continue
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps({"pid": os.getpid(), "job": job, "host": _host(),
                             "since": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
        fh.flush()
        return fh, f
    return None


# ── FIFO queue (2026-11-04) ───────────────────────────────────────────────
# noctusai-04's integrate 6 gave up after wait_s while noctusai-3d's 9
# predeploys took turns: a polling race has no fairness, so a long merged-tip
# sweep loses to whoever polls at the right moment, then ends and needs a
# human to relaunch it. Every waiter now drops a ticket; only the oldest live
# tickets (as many as there are free slots) may try a slot. Tickets of dead
# pids are swept. Best-effort across code versions: a waiter running code
# without tickets still races - it cannot jump an admitted job, only a queue.

_TICKET_SEQ = iter(range(1, 1 << 62))
_TICKET_LOCK = threading.Lock()


def _queue_dir() -> Path:
    d = Path(os.environ.get("NOCTUS_HW_QUEUE_DIR") or Path.home() / ".noctus" / "hw-queue")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _enqueue(job: str) -> Path:
    with _TICKET_LOCK:
        seq = next(_TICKET_SEQ)
    t = _queue_dir() / f"{time.time_ns():020d}-{os.getpid()}-{seq}.json"
    t.write_text(json.dumps({"pid": os.getpid(), "job": job, "host": _host(),
                             "since": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
    return t


def queue() -> list[dict[str, Any]]:
    """Live waiters, oldest first (dead-pid tickets are removed)."""
    out = []
    for t in sorted(_queue_dir().glob("*.json")):
        try:
            info = json.loads(t.read_text() or "{}")
        except (OSError, json.JSONDecodeError):
            continue                      # being written / just removed
        pid = info.get("pid")
        if not isinstance(pid, int) or not _pid_alive(pid):
            t.unlink(missing_ok=True)
            continue
        out.append({"ticket": t.name, **info})
    return out


def _queue_position(ticket: Path) -> int:
    """0-based count of live waiters ahead of `ticket`."""
    return sum(1 for w in queue() if w["ticket"] < ticket.name)


def _typical_run_s(default: float = 300.0, last_n: int = 2000) -> float:
    """Median duration of recent `ran` rows - the ETA unit."""
    p = _log_path()
    if not p.exists():
        return default
    ds = []
    for ln in p.read_text().splitlines()[-last_n:]:
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if r.get("event") == "ran" and isinstance(r.get("duration_s"), (int, float)):
            ds.append(float(r["duration_s"]))
    return sorted(ds)[len(ds) // 2] if ds else default


def shared_deadline_admit(total_wait_s: float, now: Callable[[], float] = time.monotonic,
                          slot: Callable[..., Any] | None = None):
    """An `admit` for a multi-gate run (task_branch integrate): every gate queues
    against ONE deadline instead of each giving up after its own wait_s, so a
    sweep waits its turn for as long as the caller allows - and no longer."""
    deadline = now() + total_wait_s

    def admit(job: str, **kw: Any):
        return (slot or heavy_slot)(job, wait_s=max(0.0, deadline - now()), **kw)
    return admit


@dataclass
class Admission:
    job: str
    admitted: bool
    verdict: str                      # admitted | inherited | waiting_for_slot | budget_error
    waited_s: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    blocked_by: list[str] = field(default_factory=list)
    advisories: list[str] = field(default_factory=list)
    phase: str | None = None
    outcome: dict[str, Any] = field(default_factory=dict)   # set by the caller after the run (exit_code, ...)
    queue_position: int | None = None   # 1-based place in line when last checked (None = never queued)
    # Internal fan-out cap this job runs with (vitest/playwright workers); None
    # = the job has no fan-out cap. Top-level on ran/not_admitted rows — a
    # schema contract with usage_eval (noctusai-3d), never parsed out of argv.
    job_workers: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@contextlib.contextmanager
def heavy_slot(job: str, *, wait_s: float | None = None, budget: dict[str, Any] | None = None,
               probe_fn: Callable[[float], dict[str, Any]] = probe,
               sleep: Callable[[float], None] = time.sleep,
               job_workers: Any = _AUTO) -> Iterator[Admission]:
    """Admit one heavy job. Yields an Admission; the caller MUST NOT run the job
    when ``admitted`` is False (report it as waiting_for_slot / inconclusive)."""
    if os.environ.get(_HELD_ENV):
        yield Admission(job, True, "inherited")
        return
    try:
        b = budget or load_budget()
    except BudgetError as exc:
        yield Admission(job, False, "budget_error", blocked_by=[str(exc)])
        return
    jw = fanout_cap(job, b) if job_workers is _AUTO else job_workers
    deadline = time.monotonic() + (b["wait_s"] if wait_s is None else wait_s)
    t0 = time.monotonic()
    last: dict[str, Any] = {}
    why: list[str] = ["no free slot"]
    held = None
    ticket = _enqueue(job)
    pos: int | None = None
    unit = None
    try:
        while True:
            ahead = _queue_position(ticket)
            free = int(b["max_heavy"]) - len(holders())
            if ahead + 1 != pos:      # log each move in line (only when behind someone), not each poll
                pos = ahead + 1
                if ahead > 0:
                    unit = unit if unit is not None else _typical_run_s()
                    _log({"event": "queued", "host": b["host"], "job": job, "phase": b["phase"],
                          "queue_position": pos, "ahead": ahead,
                          "eta_s": round(unit * (ahead // max(1, int(b["max_heavy"])) + 1), 1),
                          "waited_s": round(time.monotonic() - t0, 1)})
            if ahead < free:
                held = _try_slot(int(b["max_heavy"]), job)
            if held:
                last = probe_fn(b["cpu_sample_s"])
                why = evaluate(last, b)
                if not why:
                    why = memory_veto(job, last, b, max(0, len(holders()) - 1))
                if not why:
                    break
                held[0].close()
                held = None
            elif ahead >= max(free, 0) and ahead > 0:
                why = [f"queued: {ahead} waiter(s) ahead (FIFO)"]
            else:
                why = ["no free slot: " + ", ".join(f"{h.get('job')}(pid {h.get('pid')})" for h in holders())]
            if time.monotonic() >= deadline:
                adm = Admission(job, False, "waiting_for_slot", round(time.monotonic() - t0, 1),
                                last, why, advisories(last, b) if last else [], b["phase"],
                                queue_position=pos, job_workers=jw)
                _log({"event": "not_admitted", "host": b["host"], **adm.as_dict()})
                yield adm
                return
            sleep(b["poll_s"])
    finally:
        ticket.unlink(missing_ok=True)
    adm = Admission(job, True, "admitted", round(time.monotonic() - t0, 1), last, [],
                    advisories(last, b), b["phase"], queue_position=pos, job_workers=jw)
    rss0 = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    started = time.monotonic()
    prev = os.environ.get(_HELD_ENV)
    os.environ[_HELD_ENV] = str(held[1])
    try:
        yield adm
    finally:
        if prev is None:
            os.environ.pop(_HELD_ENV, None)
        else:
            os.environ[_HELD_ENV] = prev
        # ru_maxrss(CHILDREN) = largest single reaped child so far (darwin: bytes,
        # linux: KiB). Only reported when THIS job raised it, else None (unknown).
        rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        to_mb = (1 / 2**20) if sys.platform == "darwin" else (1 / 1024)
        _log({"event": "ran", "host": b["host"], **adm.as_dict(),
              "duration_s": round(time.monotonic() - started, 1),
              "children_peak_rss_mb": round(rss * to_mb, 1) if rss > rss0 else None})
        held[0].close()


# ── report ────────────────────────────────────────────────────────────────

def report(last_n: int = 5000, since: str | None = None, until: str | None = None) -> dict[str, Any]:
    """Summarize the capacity log; `since`/`until` (ISO-8601, inclusive/exclusive)
    window it — e.g. a before/after comparison around a budget change."""
    p = _log_path()
    rows = [json.loads(ln) for ln in p.read_text().splitlines()[-last_n:] if ln.strip()] if p.exists() else []
    lo = datetime.fromisoformat(since).timestamp() if since else None
    hi = datetime.fromisoformat(until).timestamp() if until else None
    rows = [r for r in rows if (lo is None or _ts(r) >= lo) and (hi is None or _ts(r) < hi)]
    samples = [r for r in rows if r.get("event") == "sample"]
    ran = [r for r in rows if r.get("event") == "ran"]
    by_job: dict[str, dict[str, Any]] = {}
    for r in ran:
        j = by_job.setdefault(r["job"], {"runs": 0, "max_duration_s": 0.0, "max_peak_rss_mb": None})
        j["runs"] += 1
        j["max_duration_s"] = max(j["max_duration_s"], r.get("duration_s") or 0)
        peak = r.get("children_peak_rss_mb")
        if peak is not None:
            j["max_peak_rss_mb"] = max(j["max_peak_rss_mb"] or 0, peak)
    by_phase: dict[str, dict[str, Any]] = {}
    for r in rows:
        ph = by_phase.setdefault(str(r.get("phase")), {"samples": 0, "overloaded": 0, "runs": 0,
                                                        "not_admitted": 0, "failed_runs": 0})
        ev = r.get("event")
        if ev == "sample":
            ph["samples"] += 1
            ph["overloaded"] += bool(r.get("overloaded"))
        elif ev == "ran":
            ph["runs"] += 1
            ph["failed_runs"] += (r.get("outcome") or {}).get("exit_code") not in (None, 0)
        elif ev == "not_admitted":
            ph["not_admitted"] += 1
    waits = [r["waited_s"] for r in ran]
    return {"log": str(p), "window": {"since": since, "until": until}, "rows": len(rows),
            "runs": len(ran),
            "not_admitted": sum(1 for r in rows if r.get("event") == "not_admitted"),
            "max_wait_s": max(waits) if waits else 0, "by_job": by_job, "by_phase": by_phase,
            "samples": len(samples),
            "overloaded_pct": round(100 * sum(1 for r in samples if r.get("overloaded")) / len(samples), 1)
            if samples else None}


# ── adaptive re-check timer + pattern-change detection ───────────────────
# Owner 2026-11-04: "measure and evaluate timing to refine our timer — wait just
# a bit more than the measured period; monitor frequently and detect patterns
# and changes of those patterns". Window = 7 days (covers the daily AND weekday
# rhythm, still adapts within a week). Re-check = median overload-episode
# length x 1.1, clamped [60 s, 1800 s]. A pattern change = the last 24 h median
# episode differs from the 7-day baseline by more than 30%.
WINDOW_S = 7 * 86400
RECENT_S = 86400
RECHECK_MARGIN = 1.1
RECHECK_MIN_S, RECHECK_MAX_S = 60, 1800
CHANGE_RATIO = 0.30


def sample(sample_s: float = 3.0) -> dict[str, Any]:
    """One monitoring tick: probe, judge against the budget, log an
    ``event=sample`` row (the series the adaptive timer learns from)."""
    st = status(sample_s)
    if st.get("status") == "budget_error":
        return st
    overloaded = bool(evaluate(st["metrics"], st["budget"]))
    aborted = _check_trial_abort(st["budget"], st["metrics"], len(st["holders"]))
    _log({"event": "sample", "host": st["budget"]["host"], "phase": st["budget"]["phase"],
          "overloaded": overloaded, "busy_slots": len(st["holders"]), "metrics": st["metrics"]})
    return {**st, "overloaded": overloaded, "trial_aborted": aborted, "timer": recheck_timer()}


def _ts(row: dict[str, Any]) -> float:
    return datetime.fromisoformat(row["ts"]).timestamp()


def _episodes(samples: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """(start_ts, duration_s) of each run of consecutive overloaded samples;
    an episode ends at the first non-overloaded sample after it."""
    out, start = [], None
    for r in samples:
        t = _ts(r)
        if r.get("overloaded") and start is None:
            start = t
        elif not r.get("overloaded") and start is not None:
            out.append((start, t - start))
            start = None
    return out


def _median(xs: list[float]) -> float | None:
    xs = sorted(xs)
    return None if not xs else (xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2)


def recheck_timer(now: float | None = None, rows: list[dict[str, Any]] | None = None,
                  default_s: float = 900) -> dict[str, Any]:
    """Recommend the next re-check interval from measured overload episodes."""
    now = now or time.time()
    if rows is None:
        p = _log_path()
        rows = [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()] if p.exists() else []
    samples = [r for r in rows if r.get("event") == "sample" and now - _ts(r) <= WINDOW_S]
    eps = _episodes(samples)
    base = _median([d for _, d in eps])
    recent = _median([d for s, d in eps if now - s <= RECENT_S])
    if base is None:
        return {"recheck_s": default_s, "basis": "default (no completed overload episode in 7 d yet)",
                "episodes_7d": 0, "samples_7d": len(samples), "pattern_changed": False}
    rec = max(RECHECK_MIN_S, min(RECHECK_MAX_S, round(base * RECHECK_MARGIN)))
    changed = recent is not None and abs(recent - base) / base > CHANGE_RATIO
    return {"recheck_s": rec, "basis": f"median 7 d overload episode {round(base)} s x {RECHECK_MARGIN}",
            "episodes_7d": len(eps), "samples_7d": len(samples), "median_episode_7d_s": round(base),
            "median_episode_24h_s": None if recent is None else round(recent),
            "pattern_changed": changed}


def status(sample_s: float = 3.0) -> dict[str, Any]:
    try:
        b = load_budget()
    except BudgetError as exc:
        return {"ok": False, "status": "budget_error", "error": str(exc)}
    m = probe(sample_s)
    why = evaluate(m, b)
    busy = holders()
    free = int(b["max_heavy"]) - len(busy)
    return {"ok": True, "status": "would_admit" if (not why and free > 0) else "would_wait",
            "budget": b, "metrics": m, "blocked_by": why + ([] if free > 0 else ["no free slot"]),
            "holders": busy, "queue": queue(), "advisories": advisories(m, b)}


# ── shell entry: run any heavy command through the gate ──────────────────

def run_command(job: str, argv: list[str], wait_s: float | None = None) -> int:
    """Exit 75 (EX_TEMPFAIL) when not admitted — never runs the command then.
    A known fan-out command (`npm test`, `npx playwright test`) gets the budget's
    worker cap here too, and the row records it whatever the job is named."""
    n = job_workers()          # an unreadable budget already yields 1
    capped = cap_worker_argv(argv, n)
    jw = n if capped != list(argv) else _AUTO
    with heavy_slot(job, wait_s=wait_s, job_workers=jw) as adm:
        if not adm.admitted:
            print(json.dumps({"hw_admission": adm.as_dict()}), file=sys.stderr)
            return 75
        code = subprocess.call(capped)
        adm.outcome["exit_code"] = code
        return code


def register(server) -> None:
    @server.tool(
        name="noctus.dev.hw_admission",
        description=(
            "Machine-wide hardware admission gate for HEAVY runs (pytest suites, vitest, e2e, vite build, "
            "gate_sweep / merged-tip legs). action='status' (default): effective per-host/phase budget "
            "(deploy/fleet/hardware-budget.json), live probe (cpu idle, reclaimable MB, swap-out/s, claude "
            "sessions), slot holders, would_admit|would_wait. action='report': capacity log summary "
            "(~/.noctus/hw-admission.ndjson) to re-tune phases from data. Shell runners use "
            "`python mcp/noctusai/tools/noctus/dev/hw_admission.py run --job <name> -- <cmd>` (exit 75 = "
            "waiting_for_slot, command not run). Load average is deliberately NOT a gate on macOS."
        ),
    )
    def _hw_admission(action: str = "status", sample_s: float = 3.0,
                      since: str | None = None, until: str | None = None) -> dict:
        if action == "report":
            return {**report(since=since, until=until), "timer": recheck_timer()}
        if action == "status":
            return status(sample_s)
        if action == "sample":
            return sample(sample_s)
        return {"ok": False, "status": "error", "error": f"unknown action {action!r} (status|sample|report)"}


if __name__ == "__main__":  # pragma: no cover - thin shell entry
    import argparse

    ap = argparse.ArgumentParser(prog="hw_admission")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--job", required=True)
    r.add_argument("--wait-s", type=float)
    r.add_argument("argv", nargs=argparse.REMAINDER)
    for name in ("status", "sample", "report"):
        sub.add_parser(name)
    a = ap.parse_args()
    if a.cmd == "run":
        cmd = a.argv[1:] if a.argv[:1] == ["--"] else a.argv
        sys.exit(run_command(a.job, cmd, a.wait_s))
    out = {"status": status, "sample": sample}.get(a.cmd, lambda: {**report(), "timer": recheck_timer()})()
    print(json.dumps(out, indent=2, default=str))
