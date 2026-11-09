"""`noctus.dev.mq_watchdog` — OFF-HOST watchdog for the CI merge queue.

WHY. The merge queue is the one path into dev, and four times it failed with nobody told:
  • 2026-11-05 ~19:57-21:28Z — the drain crashed on EVERY run (workflow-permission push
    reject); entries never changed verdict, so the in-session watcher printed nothing.
  • 2026-11-06 ~02:10Z — a second crash loop (stripped porcelain in the compose regen).
  • 2026-11-07 — 9 entries EJECTED; a dev-text watcher waited for hours, peers got no reply.
  • 2026-11-08 20:41Z-00:20Z — one entry with a stale keeper baseline failed three
    ~50-min candidate batches in a row; the steward session had ended, nothing landed for
    3.5 h, and no one knew.
Every in-session watcher dies with its session. This runs on GitHub Actions (every 10 min,
`.github/workflows/merge-queue-watchdog.yml`) and pushes to the owner through the same
channels as `prod_watchdog` (WAHA WhatsApp, Resend email).

WHAT IT REPORTS (one message per run, only when something happened)
  LANDED      an entry left the queue with a success verdict (dev sha).
  EJECTED     an entry left the queue with a failure verdict (reason + url).
  BATCH-RED   a `mq-candidate/*` CI run failed — the queue is now bisecting. Sent at the
              FIRST red, so a steward can act in minutes, not after the bisect ends.
  DRAIN-FAIL  a merge-queue.yml drain run ended failure / timed_out / startup_failure.
  STALL       the queue is non-empty and nothing has left it for MQW_STALL_MIN (90), or a
              drain run is still in progress after MQW_DRAIN_LONG_MIN (150). Reminder every
              MQW_REMIND_MIN (120); a RECOVERED line when entries move again.
  BLIND       the watchdog could not read the queue MQW_BLIND_RUNS (3) runs in a row.
Failures go to every configured channel; a success-only digest goes to WhatsApp (else
email). With `send=True`, an alert that reached no channel exits 1, so the workflow goes
red and GitHub's own failure email is the last backstop. The first run only records a
baseline (no flood of history).

🔴 STDLIB ONLY (bare `python -m tools.noctus.dev.mq_watchdog`, like prod_watchdog). Every
edge (queue reader, verdict reader, GitHub runs reader, senders, clock) is an injectable
seam — tests need no network and no monkeypatching.

Depth: `KB § PATTERNS/devops/merge-queue.md` §Watchdog.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from . import merge_queue as mq
from . import prod_watchdog as pw

STATE_VERSION = 1
DEFAULTS: dict[str, float] = {
    "MQW_STALL_MIN": 90,
    "MQW_DRAIN_LONG_MIN": 150,
    "MQW_REMIND_MIN": 120,
    "MQW_BLIND_RUNS": 3,
    "MQW_LEFT_RETRIES": 6,
}
DRAIN_WORKFLOW = "merge-queue.yml"
DRAIN_FAILURES = frozenset({"failure", "timed_out", "startup_failure"})
FAILURE_KINDS = ("ejected", "batch_red", "drain_failed", "stall", "blind")
SEEN_RUNS_CAP = 300

SnapshotFn = Callable[[], dict]
StatusFn = Callable[[str], dict]
RunsFn = Callable[[str], list]  # workflow file -> [{id, status, conclusion, head_branch, created_at, html_url}]


def thresholds(env: Mapping[str, str]) -> dict[str, float]:
    out = {}
    for k, v in DEFAULTS.items():
        raw = (env.get(k) or "").strip()
        try:
            out[k] = float(raw) if raw else v
        except ValueError as exc:
            raise ValueError(f"{k}={raw!r} is not a number") from exc
    return out


def fresh_state() -> dict:
    return {"version": STATE_VERSION, "baseline": False, "entries": {}, "leaving": {},
            "last_progress_at": None, "stall_alerted_at": None, "seen_runs": [],
            "blind_runs": 0, "blind_alerted": False, "last_run_at": None}


def load_state(path: Optional[Path]) -> tuple[dict, Optional[str]]:
    """`(state, warning)`. Missing → fresh; corrupt or unknown shape → fresh + a LOUD warning."""
    if path is None or not path.exists():
        return fresh_state(), None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return fresh_state(), f"state file {path} unreadable ({exc}) — started from a fresh baseline"
    if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
        return fresh_state(), f"state file {path} has an unknown shape — started from a fresh baseline"
    st = fresh_state()
    st.update(data)
    return st, None


def _epoch(iso: str | None) -> Optional[float]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _mins(seconds: float) -> int:
    return int(seconds // 60)


def evaluate(state: dict, snapshot: Optional[dict], snapshot_error: Optional[str],
             status_fn: StatusFn, drain_runs: list, test_runs: list, now: float,
             th: Mapping[str, float]) -> tuple[dict, dict]:
    """Pure-ish core: fold one observation into the state; return (new_state, events)."""
    st = json.loads(json.dumps(state))  # never mutate the caller's copy
    ev: dict[str, list] = {"landed": [], "ejected": [], "batch_red": [], "drain_failed": [],
                           "stall": [], "recovered": [], "blind": [], "unknown": []}
    first = not st["baseline"]
    seen = set(st["seen_runs"])

    # ── runs: drain failures + red candidate batches (first run = baseline only) ──
    for r in drain_runs:
        rid = str(r.get("id"))
        if r.get("status") == "completed" and r.get("conclusion") in DRAIN_FAILURES and rid not in seen:
            if not first:
                ev["drain_failed"].append({"run": rid, "conclusion": r.get("conclusion"), "url": r.get("html_url")})
            seen.add(rid)
    for r in test_runs:
        rid = str(r.get("id"))
        if not str(r.get("head_branch") or "").startswith(mq.CANDIDATE_PREFIX):
            continue
        if r.get("status") == "completed" and r.get("conclusion") == "failure" and rid not in seen:
            if not first:
                ev["batch_red"].append({"batch": r.get("head_branch"), "run": rid, "url": r.get("html_url")})
            seen.add(rid)
    st["seen_runs"] = sorted(seen, key=lambda x: int(x) if x.isdigit() else 0)[-SEEN_RUNS_CAP:]

    # ── queue: who left, with which verdict ──
    if snapshot is None:
        st["blind_runs"] = int(st["blind_runs"]) + 1
        if st["blind_runs"] >= th["MQW_BLIND_RUNS"] and not st["blind_alerted"]:
            ev["blind"].append({"runs": st["blind_runs"], "error": (snapshot_error or "")[:300]})
            st["blind_alerted"] = True
    else:
        if st["blind_alerted"]:
            ev["recovered"].append("the watchdog can read the queue again")
        st["blind_runs"], st["blind_alerted"] = 0, False
        current = {e["sha"]: e for e in snapshot.get("entries", [])}
        for sha, e in current.items():
            st["entries"][sha] = {"slug": e["slug"], "state": (e.get("verdict") or {}).get("state")}
            st["leaving"].pop(sha, None)
        for sha in [s for s in st["entries"] if s not in current]:
            st["leaving"][sha] = {"slug": st["entries"].pop(sha)["slug"], "tries": 0}
        for sha in list(st["leaving"]):
            slug = st["leaving"][sha]["slug"]
            try:
                v = status_fn(sha)
            except Exception as exc:  # noqa: BLE001 - a flaky read retries next run, never crashes
                v = {"state": "unavailable", "detail": f"{type(exc).__name__}: {exc}"}
            s = v.get("state")
            if s == "landed":
                ev["landed"].append({"slug": slug, "sha": sha[:9], "dev_sha": v.get("dev_sha", "")})
            elif s == "ejected":
                ev["ejected"].append({"slug": slug, "sha": sha[:9],
                                      "why": v.get("description") or v.get("detail") or "", "url": v.get("url")})
            else:
                st["leaving"][sha]["tries"] += 1
                if st["leaving"][sha]["tries"] < th["MQW_LEFT_RETRIES"]:
                    continue
                ev["unknown"].append({"slug": slug, "sha": sha[:9], "state": s})
            st["leaving"].pop(sha, None)
        if first:  # nothing "left" relative to a baseline we never had
            ev["landed"], ev["ejected"], ev["unknown"] = [], [], []

        moved = bool(ev["landed"] or ev["ejected"] or ev["unknown"])
        if moved or not current or st["last_progress_at"] is None:
            st["last_progress_at"] = now
        if moved and st["stall_alerted_at"] is not None:
            ev["recovered"].append("entries are leaving the queue again")
            st["stall_alerted_at"] = None

        # ── stall: non-empty and nothing left for too long, or a drain running too long ──
        reasons = []
        idle = now - float(st["last_progress_at"])
        if current and idle >= th["MQW_STALL_MIN"] * 60:
            reasons.append(f"{len(current)} entr{'y' if len(current) == 1 else 'ies'} waiting and nothing "
                           f"has left the queue for {_mins(idle)} min")
        for r in drain_runs:
            started = _epoch(r.get("run_started_at") or r.get("created_at"))
            if r.get("status") == "in_progress" and started and now - started >= th["MQW_DRAIN_LONG_MIN"] * 60:
                reasons.append(f"drain run {r.get('id')} in progress for {_mins(now - started)} min "
                               f"(bisecting?) {r.get('html_url') or ''}".rstrip())
        if reasons and not first:
            last = st["stall_alerted_at"]
            if last is None or now - float(last) >= th["MQW_REMIND_MIN"] * 60:
                ev["stall"] = reasons
                st["stall_alerted_at"] = now
        elif not reasons and st["stall_alerted_at"] is not None and not moved:
            ev["recovered"].append("no stall condition any more")
            st["stall_alerted_at"] = None

    st["baseline"] = True
    st["last_run_at"] = now
    return st, ev


def has_failure(ev: Mapping[str, list]) -> bool:
    return any(ev.get(k) for k in FAILURE_KINDS) or bool(ev.get("unknown"))


def compose(ev: Mapping[str, list], waiting: Optional[int]) -> Optional[tuple[str, str]]:
    """(subject, body) or None when nothing happened."""
    if not any(ev.values()):
        return None
    lines: list[str] = []
    for x in ev.get("ejected", []):
        lines.append(f"❌ EJECTED {x['slug']} ({x['sha']}): {x['why']} {x.get('url') or ''}".rstrip())
    for x in ev.get("drain_failed", []):
        lines.append(f"🔴 DRAIN-FAIL run {x['run']} ({x['conclusion']}) {x.get('url') or ''}".rstrip())
    for x in ev.get("batch_red", []):
        lines.append(f"🟠 BATCH-RED {x['batch']} — the queue is bisecting {x.get('url') or ''}".rstrip())
    for r in ev.get("stall", []):
        lines.append(f"⏸️ STALL {r}")
    for x in ev.get("blind", []):
        lines.append(f"👁️ BLIND the watchdog could not read the queue {x['runs']} runs in a row: {x['error']}")
    for x in ev.get("unknown", []):
        lines.append(f"❔ LEFT {x['slug']} ({x['sha']}) with no final verdict (last read: {x['state']})")
    for x in ev.get("landed", []):
        lines.append(f"✅ LANDED {x['slug']} ({x['sha']}) → dev {x['dev_sha']}".rstrip())
    for r in ev.get("recovered", []):
        lines.append(f"🟢 RECOVERED {r}")
    n_land, n_ej = len(ev.get("landed", [])), len(ev.get("ejected", []))
    head = []
    if n_land:
        head.append(f"{n_land} landed")
    if n_ej:
        head.append(f"{n_ej} EJECTED")
    for k, label in (("drain_failed", "DRAIN FAILED"), ("batch_red", "batch red"), ("stall", "STALLED"),
                     ("blind", "watchdog blind")):
        if ev.get(k):
            head.append(label)
    if not head and ev.get("recovered"):
        head.append("recovered")
    subject = "NoctusAI merge queue: " + ", ".join(head or ["update"])
    tail = f"\n\n{waiting} entr{'y' if waiting == 1 else 'ies'} still waiting." if waiting is not None else ""
    return subject, "\n".join(lines) + tail + "\nSteward: release_steward status · merge_queue list."


def deliver(subject: str, body: str, failure: bool, senders: Mapping[str, pw.Sender],
            cfg: Mapping[str, dict]) -> dict:
    """Failures → every configured channel; success-only → WhatsApp, else email."""
    order = ["whatsapp", "email"]
    results: dict[str, dict] = {}
    for ch in order:
        fn = senders.get(ch)
        if fn is None:
            results[ch] = {"ok": False, "detail": "NOT CONFIGURED — missing "
                           + (", ".join(cfg.get(ch, {}).get("missing") or []) or "sender")}
            continue
        try:
            ok, detail = fn(subject, body)
        except Exception as exc:  # noqa: BLE001 - a sender bug must surface, not abort the run
            ok, detail = False, f"sender raised {type(exc).__name__}: {exc}"
        results[ch] = {"ok": bool(ok), "detail": detail}
        if ok and not failure:
            break
    return {"channels": results, "delivered": any(r["ok"] for r in results.values())}


# ── real edges ────────────────────────────────────────────────────────────────
def gh_runs(repo: str, run: mq.Runner = mq._default_run, per_page: int = 30) -> RunsFn:
    # Two reads per workflow: the newest N, AND every in-progress run. A long drain is
    # buried under the cancelled pending drains each kick replaces (2026-11-08: the 3.5 h
    # run was older than the newest 30), so the newest-N page alone never sees it.
    def _page(workflow: str, query: str) -> list:
        rc, out, err = run(["gh", "api", f"repos/{repo}/actions/workflows/{workflow}/runs?{query}",
                            "--jq", "[.workflow_runs[] | {id, status, conclusion, head_branch, created_at, "
                                    "run_started_at, html_url}]"])
        if rc != 0:
            raise RuntimeError(f"gh api runs {workflow}: {err.strip()[:300]}")
        return json.loads(out or "[]")

    def _fn(workflow: str) -> list:
        merged = {r["id"]: r for r in _page(workflow, f"per_page={per_page}")}
        for r in _page(workflow, "status=in_progress&per_page=20"):
            merged.setdefault(r["id"], r)
        return list(merged.values())
    return _fn


def run(state_path: Optional[Path], send: bool = False, *, env: Optional[Mapping[str, str]] = None,
        snapshot_fn: Optional[SnapshotFn] = None, status_fn: Optional[StatusFn] = None,
        runs_fn: Optional[RunsFn] = None, senders: Optional[Mapping[str, pw.Sender]] = None,
        clock: Callable[[], float] = time.time, workdir: Optional[str] = None) -> dict:
    env = os.environ if env is None else env
    th = thresholds(env)
    wd = workdir or os.getcwd()
    repo = (env.get("GITHUB_REPOSITORY") or "").strip() or mq._repo_from_remote(mq._default_run, wd)
    snapshot_fn = snapshot_fn or (lambda: mq.queue_snapshot(repo, workdir=wd))
    status_fn = status_fn or (lambda sha: mq.read_status(repo, sha))
    runs_fn = runs_fn or gh_runs(repo)
    state, warning = load_state(state_path)
    warnings = [warning] if warning else []

    snapshot, snap_err = None, None
    try:
        snapshot = snapshot_fn()
        if snapshot.get("status") == "error":
            snap_err, snapshot = f"{snapshot.get('error_type')}: {snapshot.get('error')}", None
    except Exception as exc:  # noqa: BLE001 - counted as a blind run, never a crash
        snap_err = f"{type(exc).__name__}: {exc}"
    runs: dict[str, list] = {}
    for wf in (DRAIN_WORKFLOW, mq.CI_WORKFLOW):
        try:
            runs[wf] = runs_fn(wf)
        except Exception as exc:  # noqa: BLE001
            runs[wf] = []
            warnings.append(f"could not list {wf} runs: {type(exc).__name__}: {exc}")

    new_state, ev = evaluate(state, snapshot, snap_err, status_fn, runs[DRAIN_WORKFLOW],
                             runs[mq.CI_WORKFLOW], clock(), th)
    waiting = len(snapshot.get("entries", [])) if snapshot else None
    msg = compose(ev, waiting)
    failure = has_failure(ev)
    delivery = None
    exit_code = 0
    if msg and send:
        cfg = pw.channel_config(env)
        delivery = deliver(msg[0], msg[1], failure, pw.make_senders(env) if senders is None else senders, cfg)
        if not delivery["delivered"]:
            exit_code = 1
            if failure:  # keep the failure un-acknowledged so the next run retries it
                new_state = state
                warnings.append("a FAILURE alert reached no channel — state not advanced, the next run retries")
    if state_path is not None and new_state is not state:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = state_path.with_suffix(state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(new_state, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, state_path)
    return {"status": "ok", "events": ev, "message": msg, "failure": failure, "sent": bool(msg and send),
            "delivery": delivery, "waiting": waiting, "warnings": warnings, "exit_code": exit_code,
            "baseline_only": not state["baseline"]}


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="mq_watchdog", description=__doc__.split("\n", 1)[0])
    p.add_argument("--state", type=Path, default=None, help="JSON state file (omit = stateless dry check)")
    p.add_argument("--send", action="store_true", help="send real alerts (default: dry run)")
    a = p.parse_args(argv)
    try:
        rep = run(a.state, send=a.send)
    except ValueError as exc:
        print(f"mq-watchdog: config error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(rep, indent=2, default=str, ensure_ascii=False))
    for w in rep["warnings"]:
        print(f"::warning::{w}", file=sys.stderr)
    return int(rep["exit_code"])


def register(server) -> None:  # pragma: no cover - thin MCP wrapper
    @server.tool(
        name="noctus.dev.mq_watchdog",
        description=(
            "OFF-HOST merge-queue watchdog (the CI job runs it every 10 min, independent of any "
            "steward session). One run folds the queue + drain/candidate runs into a state file and "
            "reports LANDED / EJECTED / BATCH-RED (first red candidate batch = bisect started) / "
            "DRAIN-FAIL / STALL (non-empty with nothing leaving for 90 min, or a drain running "
            ">150 min) / BLIND (queue unreadable 3 runs). Default is a DRY check (no send; state "
            "touched only when state_path is given); send=True pushes WhatsApp/email like "
            "prod_watchdog. KB § PATTERNS/devops/merge-queue.md."
        ),
    )
    def _mq_watchdog(state_path: Optional[str] = None, send: bool = False) -> dict:
        return run(Path(state_path) if state_path else None, send=send)


if __name__ == "__main__":
    sys.exit(main())
