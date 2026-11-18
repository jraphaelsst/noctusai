"""steward_feed: the release steward's ONE feed - the merge-queue watch plus the handed-run registry.

WHY (2026-11-16): the steward ran `--merge-queue watch` AND three hand-written loops (`gh run view` every 120s per
handed-off CI run, then `--task-branch enqueue` when green). Each handoff meant a new loop (N=3), a grep over enqueue JSON
matched nested `"class"` lines and hid the status, the lease went stale during long passes, every landing needed a manual
`task_branch landed`, a red cost a manual `--log-failed` fetch, a `conflict` ejection that was already on dev needed a
human, the 30-min Monitor was re-armed by hand, and the shared 5000/h GitHub quota ran dry.

Now a handoff is ONE registry append (`--steward-feed register`), and the one watch command also:
  * polls every registered run (>=120s apart, conditional GET through the ci_verdict `GithubClient` seam) and prints
    `RUN <slug> <run> -> success|failure|cancelled <sha> rate_remaining=<n>` (a red adds the failing job names and the
    first FAILED/error line, from ONE log fetch);
  * on success heartbeats the steward lease, runs `task_branch enqueue` and prints `ENQ <slug> -> queued|refused:<why>|
    needs_resync:<item>` (one line, never JSON; `after:<slug>` registrations wait for that slug's own enqueue);
  * after `MQ-LEFT ... landed` runs `task_branch landed` itself and prints `LANDED-RECORDED <slug> <dev sha>`;
  * an ejected `conflict` whose content is already on dev prints `MQ-SUPERSEDED` instead of waiting for a human;
  * `--idle-exit` prints `MQ-IDLE` and exits 0 when the queue is empty and no run is pending (bg_run `--done-when`);
  * backs off to 300s when the quota left is under 500.

Seams (no module function is ever patched): `GithubClient` (ci_verdict), and the callables `enqueue_fn`, `landed_fn`,
`heartbeat_fn`, `superseded_fn`, `clock`, `emit` that the Real wiring (`live_feed`) fills.

KB: PATTERNS/devops/release-steward.md (§ 7b).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

MIN_POLL_S = 120.0
BACKOFF_POLL_S = 300.0
LOW_QUOTA = 500
REGISTRY_NAME = "steward-handed-runs.ndjson"
_CLI = Path(__file__).resolve().parents[3] / "cli.py"


def default_registry(env: dict[str, str] | None = None) -> Path:
    e = env if env is not None else os.environ
    return Path(e.get("NOCTUS_STEWARD_DIR") or Path.home() / ".noctus") / REGISTRY_NAME


class HandedRuns:
    """Append-only registry: `register` rows and `done` rows; the pending set is the fold. One line per handoff."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn line is skipped; the append below is a single write
        return rows

    def _append(self, row: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    def register(self, slug: str, run: str, sha: str, after: str | None = None) -> dict[str, Any]:
        row = {"kind": "register", "slug": slug, "run": str(run), "sha": sha, **({"after": after} if after else {}),
               "at": time.time()}
        self._append(row)
        return row

    def mark_done(self, slug: str, outcome: str) -> None:
        self._append({"kind": "done", "slug": slug, "outcome": outcome, "at": time.time()})

    def state(self) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """(pending registrations in order, {slug: outcome} of finished ones). A re-registered slug starts afresh."""
        pending: dict[str, dict[str, Any]] = {}
        done: dict[str, str] = {}
        for r in self._rows():
            if r.get("kind") == "register":
                pending[r["slug"]] = r
                done.pop(r["slug"], None)
            elif r.get("kind") == "done" and r.get("slug") in pending:
                done[r["slug"]] = str(r.get("outcome") or "")
                pending.pop(r["slug"], None)
        return list(pending.values()), done

    def pending(self) -> list[dict[str, Any]]:
        return self.state()[0]


def failure_summary(log: str) -> tuple[list[str], str]:
    """(failing job names in first-seen order, the first FAILED/error line) from `gh run view --log-failed` text
    (`job<TAB>step<TAB>timestamp text` rows)."""
    jobs: list[str] = []
    first = ""
    for raw in log.splitlines():
        parts = raw.split("\t", 2)
        if len(parts) == 3 and parts[0] and parts[0] not in jobs:
            jobs.append(parts[0])
        text = parts[2] if len(parts) == 3 else raw
        low = text.lower()
        if not first and ("failed" in low or "error" in low) and text.strip():
            first = text.split("Z ", 1)[-1].strip()[:200] if "Z " in text[:40] else text.strip()[:200]
    return jobs, first


def _fmt_failure(jobs: list[str], first: str) -> str:
    out = ""
    if jobs:
        out += " jobs=" + ",".join(jobs[:6])
    if first:
        out += f" first={first!r}"
    return out


class StewardFeed:
    """Folds the handed-run registry into the watch: `tick` (per poll), `on_left`, `idle`, `interval`."""

    def __init__(self, registry: HandedRuns, client: Any, *,
                 enqueue_fn: Callable[[str, str], dict[str, Any]],
                 landed_fn: Callable[[str], dict[str, Any]],
                 heartbeat_fn: Callable[[], dict[str, Any]],
                 reconcile_fn: Callable[[], Any] | None = None,
                 superseded_fn: Callable[[str], str | None],
                 emit: Callable[[str], None] = lambda line: print(line, flush=True),
                 clock: Callable[[], float] = time.monotonic,
                 base_interval: float = 60.0) -> None:
        self.reg, self.client = registry, client
        self.enqueue_fn, self.landed_fn = enqueue_fn, landed_fn
        self.heartbeat_fn, self.superseded_fn = heartbeat_fn, superseded_fn
        self.reconcile_fn = reconcile_fn
        self.emit, self.clock, self.base_interval = emit, clock, base_interval
        self._last_poll: dict[str, float] = {}
        self._rate: int | None = None

    # -- cadence ---------------------------------------------------------------------------------------------
    def interval(self) -> float:
        low = self._rate is not None and self._rate < LOW_QUOTA
        return max(self.base_interval, BACKOFF_POLL_S) if low else self.base_interval

    def _poll_gap(self) -> float:
        return BACKOFF_POLL_S if self._rate is not None and self._rate < LOW_QUOTA else MIN_POLL_S

    # -- per poll --------------------------------------------------------------------------------------------
    def tick(self) -> None:
        if self.reconcile_fn is not None:  # done tasks are marked landed by the watch itself, never by memory
            try:
                for r in self.reconcile_fn() or []:
                    self.emit(f"AUTO-LANDED {r['slug']} {str(r.get('landed_detected') or '')[:9]} (already in origin/dev)")
            except Exception as exc:  # noqa: BLE001 - loud, never stops the watch
                self.emit(f"AUTO-RECONCILE-ERROR {str(exc)[:120]}")
        pending, done = self.reg.state()
        for r in pending:
            slug = r["slug"]
            after = r.get("after")
            if after and after not in done and any(p["slug"] == after for p in pending):
                continue  # ordered behind a slug that has not finished its own run/enqueue yet
            now = self.clock()
            if slug in self._last_poll and now - self._last_poll[slug] < self._poll_gap():
                continue
            self._last_poll[slug] = now
            self._poll_one(r)

    def _poll_one(self, r: dict[str, Any]) -> None:
        slug, rid, sha = r["slug"], str(r["run"]), r["sha"]
        try:
            run = self.client.run_cached(rid)
            self._rate = self.client.rate_remaining()
        except Exception as exc:  # noqa: BLE001 - a failed read is reported and retried next poll
            self.emit(f"MQ-WATCH-ERROR run {slug} {rid} {type(exc).__name__}: {str(exc)[:200]}")
            return
        if not run:
            self.emit(f"RUN {slug} {rid} -> missing {sha[:9]} (not found on GitHub)")
            self.reg.mark_done(slug, "missing")
            return
        if run.get("status") != "completed":
            return
        concl = str(run.get("conclusion") or "unknown")
        rate = f" rate_remaining={self._rate}" if self._rate is not None else ""
        tested = str(run.get("head_sha") or "")
        if tested != sha:
            self.emit(f"RUN {slug} {rid} -> {concl} {tested[:9]} refused: tested {tested[:9]}, registered {sha[:9]}{rate}")
            self.reg.mark_done(slug, "sha_mismatch")
            return
        if concl != "success":
            detail = ""
            try:
                detail = _fmt_failure(*failure_summary(self.client.failed_log(rid)))
            except Exception as exc:  # noqa: BLE001 - the verdict line still goes out
                detail = f" log-unavailable={type(exc).__name__}"
            self.emit(f"RUN {slug} {rid} -> {concl} {sha[:9]}{rate}{detail}")
            self.reg.mark_done(slug, concl)
            return
        self.emit(f"RUN {slug} {rid} -> success {sha[:9]}{rate}")
        self._enqueue(slug, rid)

    def _enqueue(self, slug: str, rid: str) -> None:
        try:
            hb = self.heartbeat_fn()  # right before the enqueue: a long pass must not let the lease go stale
            if not hb.get("ok", True):
                self.emit(f"HEARTBEAT-FAILED {slug}: {str(hb.get('error') or hb)[:200]}")
        except Exception as exc:  # noqa: BLE001
            self.emit(f"HEARTBEAT-FAILED {slug}: {type(exc).__name__}: {str(exc)[:200]}")
        try:
            res = self.enqueue_fn(slug, f"gh-run:{rid}")
        except Exception as exc:  # noqa: BLE001
            res = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        status = str(res.get("status") or "unknown")  # TOP-LEVEL key only: nested `class` lines never leak in
        if status in ("queued", "up_to_date", "planned"):
            self.emit(f"ENQ {slug} -> queued")
            self.reg.mark_done(slug, "enqueued")
        elif status == "needs_resync":
            self.emit(f"ENQ {slug} -> needs_resync:{_first_failing(res)}")
            self.reg.mark_done(slug, "needs_resync")
        elif status == "pending_ci":
            self.emit(f"ENQ {slug} -> refused:pending_ci {_first_failing(res)}".rstrip())
            self.reg.mark_done(slug, "refused")
        else:
            why = res.get("refused") or res.get("error") or status
            self.emit(f"ENQ {slug} -> refused:{str(why)[:200]}")
            self.reg.mark_done(slug, "refused")

    # -- from the queue watch --------------------------------------------------------------------------------
    def on_left(self, slug: str, sha: str, verdict: dict[str, Any]) -> None:
        if verdict.get("state") == "landed":
            res = self.landed_fn(slug)
            if res.get("status") == "landed" or res.get("ok"):
                self.emit(f"LANDED-RECORDED {slug} {res.get('dev_sha') or verdict.get('dev_sha', '')}".rstrip())
            else:
                self.emit(f"LANDED-ERROR {slug} {str(res.get('error') or res.get('status') or res)[:200]}")
            return
        why = str(verdict.get("description") or verdict.get("detail") or "")
        if "conflict" in why.lower():
            how = self.superseded_fn(sha)
            if how:
                self.emit(f"MQ-SUPERSEDED {slug} {sha[:9]} -> superseded ({how}): already on dev, nothing to re-enqueue")

    def idle(self) -> bool:
        return not self.reg.pending()


def _first_failing(res: dict[str, Any]) -> str:
    for x in res.get("failing") or []:
        if isinstance(x, dict):
            x = x.get("name") or x.get("detail") or json.dumps(x)[:80]
        return str(x)[:160]
    return "contract"


# -- Real wiring (subprocess seams; argv lists only) ---------------------------------------------------------
def _cli_json(args: list[str], cwd: str, timeout: int = 900) -> dict[str, Any]:
    r = subprocess.run([sys.executable, str(_CLI), *args], cwd=cwd, capture_output=True, text=True,  # noqa: S603
                       timeout=timeout, check=False)
    try:
        d = json.loads(r.stdout[r.stdout.index("{"):r.stdout.rindex("}") + 1])
    except ValueError:
        return {"status": "error", "error": f"unparseable cli output rc={r.returncode}: {(r.stderr or r.stdout)[-200:]}"}
    return d if isinstance(d, dict) else {"status": "error", "error": "cli output is not an object"}


def real_enqueue(cwd: str) -> Callable[[str, str], dict[str, Any]]:
    return lambda slug, ref: _cli_json(["--task-branch", "enqueue", "--task-branch-slug", slug, "--task-branch-confirm",
                                        "--task-branch-verdict-ref", ref], cwd)


def real_landed(cwd: str) -> Callable[[str], dict[str, Any]]:
    return lambda slug: _cli_json(["--task-branch", "landed", "--task-branch-slug", slug, "--task-branch-confirm"], cwd)


def real_reconcile() -> Callable[[], list[dict[str, Any]]]:
    def go() -> list[dict[str, Any]]:
        from tools.noctus.dev.release_steward import StewardStore  # lazy: heavy module
        return StewardStore().auto_reconcile()
    return go


def real_heartbeat() -> Callable[[], dict[str, Any]]:
    def beat() -> dict[str, Any]:
        from tools.noctus.dev.release_steward import SESSION_ENV, StewardStore  # lazy: heavy module
        return StewardStore().heartbeat(os.environ.get(SESSION_ENV))
    return beat


def real_superseded(cwd: str) -> Callable[[str], str | None]:
    """`patch-equivalent` (every commit of sha is in `git cherry origin/dev` as `-`) or `content-equal` (the files sha
    touched are byte-equal on origin/dev); None when neither holds or sha is not in the local object store."""
    def g(*a: str) -> tuple[int, str]:
        r = subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
        return r.returncode, r.stdout

    def check(sha: str) -> str | None:
        if g("cat-file", "-e", f"{sha}^{{commit}}")[0] != 0:
            return None
        rc, out = g("cherry", "origin/dev", sha)
        lines = [x for x in out.splitlines() if x.strip()]
        if rc == 0 and lines and all(x.startswith("-") for x in lines):
            return "patch-equivalent"
        rc, mb = g("merge-base", "origin/dev", sha)
        if rc != 0:
            return None
        rc, names = g("diff", "--name-only", mb.strip(), sha)
        files = [f for f in names.splitlines() if f]
        if rc == 0 and files and g("diff", "--quiet", "origin/dev", sha, "--", *files)[0] == 0:
            return "content-equal"
        return None
    return check
