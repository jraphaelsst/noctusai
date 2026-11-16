"""ci_verdict: delivery-contract item 5 judged by a GitHub Actions `test.yml` run, not a local machine run.

WHY (2026-11-16): the local CI-parity run needs a machine-wide heavy slot on an 8 GB laptop shared by many sessions;
filings came back UNMEASURED or timed out. The same suites run on GitHub, so item 5 now accepts `gh-run:<databaseId>`.

NOT forgeable: `judge` resolves the id against GitHub (repo from `git remote get-url origin`, workflow path, full head
sha, status/conclusion) - a string a caller typed proves nothing. The GitHub access is a seam (`GithubClient`:
Real shells `gh`, Fake for tests, `make_client` factory); no module function is ever patched.

QUOTA BY CONSTRUCTION (2026-11-16: the account's REST core quota, 5000/h, hit 0 and every session got 403): this class is
THE GitHub-call seam for repo code. It counts calls (`api_calls`), reads the free `gh api rate_limit` before a dispatch
or a watch (`ensure_quota`, floor `QUOTA_FLOOR`), turns a 403 rate-limit into `RateLimited` (never a retry storm), and
waits for a run with `wait_for_run` instead of `gh run watch`: that command re-fetches the run, its jobs and per-job
annotations every interval (>= 2 + jobs REST calls per tick, per watcher). `wait_for_run` polls ONE endpoint
(`actions/runs/<id>`) with an ETag (`If-None-Match`; a 304 is not counted against the primary limit) every 60s,
backing off 60 -> 120 -> 300s. Keeper `check_gh_calls_via_seam` refuses `gh run watch` anywhere and a new `["gh", ...]`
argv outside this file (shrink-only baseline for the named legacy sites).

KB: PATTERNS/devops/release-steward.md (item 5) · PATTERNS/devops/hardware-admission-budget.md (GitHub quota).
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

WORKFLOW_FILE = "test.yml"
WORKFLOW_PATH = ".github/workflows/test.yml"
REF_RE = re.compile(r"^gh-run:(\d+)$")
PENDING_PREFIX = "CI running:"
GREEN, RED, PENDING, INVALID = "green", "red", "pending", "invalid"
_FULL_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_REMOTE_RE = re.compile(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")


class CiVerdictError(RuntimeError):
    """gh unavailable / unauthenticated / a refused precondition: surfaced loudly, never swallowed."""


QUOTA_FLOOR = 500          # below this many remaining core calls: degrade loudly, spend nothing
WATCH_BACKOFF_S = (60.0, 120.0, 300.0)  # poll gaps for wait_for_run; the last value repeats
_RATE_PAT = re.compile(r"rate limit|secondary rate|abuse detection|HTTP 429", re.I)


class RateLimited(CiVerdictError):
    """GitHub refused for quota (403/429 rate limit, or remaining below the floor). `reset_epoch` = when it lifts."""

    def __init__(self, message: str, remaining: int | None = None, reset_epoch: float | None = None) -> None:
        super().__init__(message)
        self.remaining, self.reset_epoch = remaining, reset_epoch


def reset_clock(reset_epoch: float | None) -> str:
    if not reset_epoch:
        return "an unknown time"
    return time.strftime("%H:%M:%SZ", time.gmtime(reset_epoch))


def parse_rate(out: str) -> dict[str, float] | None:
    """{remaining, limit, reset} from `gh api rate_limit` output (the `.resources.core` object or the whole body)."""
    try:
        d = json.loads(out)
    except (ValueError, TypeError):
        return None
    core = (d.get("resources") or {}).get("core") if isinstance(d, dict) else None
    core = core or (d if isinstance(d, dict) and "remaining" in d else None)
    if not core or "remaining" not in core:
        return None
    return {"remaining": int(core["remaining"]), "limit": int(core.get("limit") or 0), "reset": float(core.get("reset") or 0)}


def quota_pause_s(run: Callable[..., tuple[int, str, str]], *, floor: int = QUOTA_FLOOR, now: Callable[[], float] = time.time,
                  cwd: str | None = None) -> tuple[float, dict[str, float] | None]:
    """(seconds to wait, rate) for a long-running watcher that shells `gh` through `run(args, cwd=)`: 0 when the free
    `gh api rate_limit` shows `floor`+ calls left (or cannot be read: an unreadable meter never blocks work)."""
    try:
        rc, out, _e = run(["gh", "api", "rate_limit"], cwd=cwd)
    except Exception:  # noqa: BLE001 - an unreadable meter must not stop a watcher
        return 0.0, None
    rate = parse_rate(out) if rc == 0 else None
    if rate is None or rate["remaining"] >= floor:
        return 0.0, rate
    return max(0.0, rate["reset"] - now()) + 5.0, rate


class GithubClient(Protocol):
    def repo(self) -> str: ...
    def merge_base(self, head: str) -> str | None: ...
    def branch_tip(self, branch: str) -> str | None: ...
    def run(self, run_id: str) -> dict[str, Any] | None: ...
    def runs_for_head(self, head: str) -> list[dict[str, Any]]: ...
    def dispatch(self, branch: str, base: str | None) -> None: ...


def _sh(args: list[str], cwd: str | None, timeout: int = 60) -> tuple[int, str, str]:
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False)  # noqa: S603
    except FileNotFoundError as exc:
        raise CiVerdictError(f"`{args[0]}` is not installed ({exc}): the GitHub verdict needs the gh CLI") from exc
    except subprocess.TimeoutExpired as exc:
        raise CiVerdictError(f"`{' '.join(args[:3])}` timed out after {timeout}s") from exc
    return r.returncode, r.stdout, r.stderr


class RealGithubClient:
    """Shells `gh` (authenticated locally) and `git`; argv lists only, no shell."""

    def __init__(self, cwd: str | None = None, runner: Callable[..., tuple[int, str, str]] = _sh,
                 repo: str | None = None) -> None:
        """`repo` pins owner/name (else derived from `git remote get-url origin`)."""
        self.cwd, self._sh, self._repo = cwd, runner, repo
        self.api_calls = 0                  # every `gh` call this client made (rate_limit reads counted in free_calls)
        self.free_calls = 0
        self.rate_remaining: int | None = None  # last quota reading (None until `rate()` ran)
        self.rate_reset: float | None = None
        self._etags: dict[str, tuple[str, Any]] = {}

    def _exec(self, args: list[str], timeout: int = 60, *, free: bool = False) -> tuple[int, str, str]:
        """THE choke point for `gh`: counts the call and turns a quota refusal into `RateLimited` (never a retry loop)."""
        if free:
            self.free_calls += 1
        else:
            self.api_calls += 1
        rc, out, err = self._sh(["gh", *args], self.cwd, timeout) if timeout != 60 else self._sh(["gh", *args], self.cwd)
        if rc != 0 and not free and _RATE_PAT.search(f"{err}\n{out}"):
            rate = self._rate_quiet()
            reset = rate["reset"] if rate else None
            raise RateLimited(f"GitHub API quota exhausted ({(err or out).strip()[:120]}); it resets at {reset_clock(reset)}",
                              rate["remaining"] if rate else 0, reset)
        return rc, out, err

    def _rate_quiet(self) -> dict[str, float] | None:
        try:
            return self.rate()
        except CiVerdictError:
            return None

    def rate(self) -> dict[str, float]:
        """The core quota via `gh api rate_limit` (free: it is not counted against the limit)."""
        rc, out, err = self._exec(["api", "rate_limit"], free=True)
        rate = parse_rate(out) if rc == 0 else None
        if rate is None:
            raise CiVerdictError(f"cannot read the GitHub quota (gh api rate_limit rc={rc}): {(err or out).strip()[-200:]}")
        self.rate_remaining, self.rate_reset = int(rate["remaining"]), rate["reset"]
        return rate

    def ensure_quota(self, floor: int = QUOTA_FLOOR, now: Callable[[], float] = time.time) -> dict[str, float]:
        """Raise `RateLimited` (naming the quota and the reset time) when fewer than `floor` core calls remain."""
        rate = self.rate()
        if rate["remaining"] < floor:
            raise RateLimited(f"GitHub API quota is {int(rate['remaining'])}/{int(rate['limit'])} (floor {floor}); it resets at "
                              f"{reset_clock(rate['reset'])} (in {int(max(0.0, rate['reset'] - now()))}s)",
                              int(rate["remaining"]), rate["reset"])
        return rate

    def _gh(self, *args: str) -> Any:
        rc, out, err = self._exec(list(args))
        if rc != 0:
            raise CiVerdictError(f"gh {' '.join(args[:2])} failed (rc={rc}): {(err or out).strip()[-300:]} "
                                 "(is `gh auth status` green?)")
        return json.loads(out) if out.strip() else None

    def run_conditional(self, run_id: str) -> tuple[dict[str, Any] | None, bool]:
        """(run, changed). Sends the remembered ETag as If-None-Match: an unchanged run is a 304 (not counted by GitHub)
        and returns (the cached run, False). Headers come from `gh api -i`."""
        path = f"repos/{self.repo()}/actions/runs/{run_id}"
        cached = self._etags.get(path)
        args = ["api", "-i", path] + (["-H", f"If-None-Match: {cached[0]}"] if cached else [])
        rc, out, err = self._exec(args)
        head, _sep, body = out.replace("\r\n", "\n").partition("\n\n")
        status_line = head.splitlines()[0] if head.startswith("HTTP/") else ""
        code = int(status_line.split()[1]) if len(status_line.split()) > 1 and status_line.split()[1].isdigit() else 0
        if code == 304 and cached:
            return cached[1], False
        if rc != 0 or code >= 400 or not code:
            raise CiVerdictError(f"gh api runs/{run_id} failed (rc={rc}, http={code}): {(err or out).strip()[-300:]} "
                                 "(is `gh auth status` green?)")
        run = json.loads(body) if body.strip() else None
        etag = next((ln.split(":", 1)[1].strip() for ln in head.splitlines() if ln.lower().startswith("etag:")), "")
        if etag:
            self._etags[path] = (etag, run)
        return run, True

    def repo(self) -> str:
        if self._repo is None:
            rc, out, err = self._sh(["git", "remote", "get-url", "origin"], self.cwd)
            m = _REMOTE_RE.search(out.strip()) if rc == 0 else None
            if not m:
                raise CiVerdictError(f"cannot derive owner/repo from `git remote get-url origin` ({(err or out).strip()[:120]})")
            self._repo = f"{m.group(1)}/{m.group(2)}"
        return self._repo

    def merge_base(self, head: str) -> str | None:
        rc, out, _e = self._sh(["git", "merge-base", "origin/dev", head], self.cwd)
        return out.strip() or None if rc == 0 else None

    def branch_tip(self, branch: str) -> str | None:
        rc, out, _e = self._sh(["git", "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}^{{commit}}"], self.cwd)
        return out.strip() or None if rc == 0 else None

    def run(self, run_id: str) -> dict[str, Any] | None:
        return self._gh("api", f"repos/{self.repo()}/actions/runs/{run_id}")

    def runs_for_head(self, head: str) -> list[dict[str, Any]]:
        d = self._gh("api", f"repos/{self.repo()}/actions/workflows/{WORKFLOW_FILE}/runs?head_sha={head}&per_page=30")
        return list((d or {}).get("workflow_runs") or [])

    def dispatch(self, branch: str, base: str | None) -> None:
        args = ["workflow", "run", WORKFLOW_FILE, "--ref", branch, "-R", self.repo()]
        if base:
            args += ["-f", f"base={base}"]
        rc, out, err = self._exec(args)
        if rc != 0:
            raise CiVerdictError(f"gh workflow run failed (rc={rc}): {(err or out).strip()[-300:]}")


    def remote_tip(self, branch: str) -> str | None:
        """The AUTHORITATIVE pushed tip (`git ls-remote`), not the possibly stale local origin/<branch> ref."""
        rc, out, _e = self._sh(["git", "ls-remote", "origin", f"refs/heads/{branch}"], self.cwd)
        return (out.split() or [None])[0] if rc == 0 else None

    def workflow_exists(self, workflow: str) -> bool:
        rc, out, err = self._exec(["api", f"repos/{self.repo()}/actions/workflows/{workflow}"])
        if rc == 0:
            return True
        if "404" in (err or out) or "Not Found" in (err or out):
            return False
        raise CiVerdictError(f"gh api workflows/{workflow} failed (rc={rc}): {(err or out).strip()[-300:]} "
                             "(is `gh auth status` green?)")

    def dispatch_workflow(self, workflow: str, branch: str, inputs: dict[str, str]) -> None:
        args = ["workflow", "run", workflow, "--ref", branch, "-R", self.repo()]
        for k, v in inputs.items():
            args += ["-f", f"{k}={v}"]
        rc, out, err = self._exec(args)
        if rc != 0:
            raise CiVerdictError(f"gh workflow run {workflow} failed (rc={rc}): {(err or out).strip()[-300:]}")

    def runs_for_workflow(self, workflow: str, branch: str) -> list[dict[str, Any]]:
        d = self._gh("api", f"repos/{self.repo()}/actions/workflows/{workflow}/runs"
                            f"?branch={branch}&event=workflow_dispatch&per_page=30")
        return list((d or {}).get("workflow_runs") or [])

    def watch(self, run_id: str, out: Callable[[str], None], timeout_s: float,
              sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
              on_quota: str = "sleep") -> bool:
        """Wait for a run to complete; False when `timeout_s` elapsed first. NEVER `gh run watch` (see module docstring):
        ONE conditional GET on the run every 60s (backoff 60/120/300s). A quota refusal sleeps until the reset, loudly
        (long-lived watchers), or with `on_quota="raise"` re-raises `RateLimited` so the caller can fall back (remote_test)."""
        t0, tick, last = clock(), 0, None
        while True:
            try:
                run, _changed = self.run_conditional(run_id)
            except RateLimited as exc:
                if on_quota == "raise":
                    raise
                wait = max(0.0, (exc.reset_epoch or time.time()) - time.time()) + 5.0
                if clock() - t0 + wait > timeout_s:
                    out(f"GITHUB QUOTA: {exc}; the reset is beyond the {int(timeout_s)}s wait budget, giving up the watch (run {run_id} keeps running)")
                    return False
                out(f"GITHUB QUOTA: {exc}; sleeping {int(wait)}s until the reset, then resuming the watch")
                sleep(wait)
                continue
            state = (run or {}).get("status"), (run or {}).get("conclusion")
            if state != last:
                last = state
                out(f"run {run_id}: {state[0]}" + (f" ({state[1]})" if state[1] else ""))
            if state[0] == "completed":
                return True
            gap = WATCH_BACKOFF_S[min(tick, len(WATCH_BACKOFF_S) - 1)]
            tick += 1
            if clock() - t0 + gap > timeout_s:
                return False
            sleep(gap)

    def run_log(self, run_id: str) -> str:
        rc, out, err = self._exec(["run", "view", str(run_id), "--log", "-R", self.repo()], timeout=300)
        if rc != 0:
            raise CiVerdictError(f"gh run view --log failed (rc={rc}): {(err or out).strip()[-300:]}")
        return out


@dataclass
class FakeGithubClient:
    """In-memory GitHub for tests: `runs` = {id: run dict}; dispatch() appends a queued run on `branch`'s tip."""
    repo_name: str = "acme/noc"
    tips: dict[str, str] = field(default_factory=dict)
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    base: str | None = "b" * 40
    dispatched: list[tuple[str, str | None]] = field(default_factory=list)
    next_id: int = 1000
    fail: str | None = None
    api_calls: int = 0
    rate_remaining: int | None = 5000
    rate_reset: float | None = None
    quota: tuple[int, float] | None = None  # (remaining, reset_epoch) the fake meter reports; None = plenty
    watched: list[str] = field(default_factory=list)

    def rate(self) -> dict[str, float]:
        rem, reset = self.quota if self.quota else (5000, 0.0)
        self.rate_remaining, self.rate_reset = rem, reset
        return {"remaining": rem, "limit": 5000, "reset": reset}

    def ensure_quota(self, floor: int = QUOTA_FLOOR, now: Callable[[], float] = time.time) -> dict[str, float]:
        rate = self.rate()
        if rate["remaining"] < floor:
            raise RateLimited(f"GitHub API quota is {int(rate['remaining'])}/5000 (floor {floor}); it resets at "
                              f"{reset_clock(rate['reset'])}", int(rate["remaining"]), rate["reset"])
        return rate

    watch_quota_error: RateLimited | None = None

    def watch(self, run_id: str, out: Callable[[str], None], timeout_s: float, **_kw: Any) -> bool:
        if self.watch_quota_error:
            raise self.watch_quota_error
        self.watched.append(str(run_id))
        r = self.runs.get(str(run_id)) or {}
        out(f"run {run_id}: {r.get('status')}")
        return r.get("status") == "completed"

    def repo(self) -> str:
        if self.fail:
            raise CiVerdictError(self.fail)
        return self.repo_name

    def merge_base(self, head: str) -> str | None:
        return self.base

    def branch_tip(self, branch: str) -> str | None:
        return self.tips.get(branch)

    def run(self, run_id: str) -> dict[str, Any] | None:
        self.repo()
        self.api_calls += 1
        return self.runs.get(str(run_id))

    def runs_for_head(self, head: str) -> list[dict[str, Any]]:
        self.repo()
        self.api_calls += 1
        return [r for r in self.runs.values() if r.get("head_sha") == head]

    def dispatch(self, branch: str, base: str | None) -> None:
        self.repo()
        self.dispatched.append((branch, base))
        self.next_id += 1
        self.runs[str(self.next_id)] = make_run(self.next_id, self.tips[branch], repo=self.repo_name,
                                                event="workflow_dispatch", status="queued")


def make_run(rid: int | str, head: str, *, repo: str = "acme/noc", status: str = "completed", conclusion: str | None = None,
             event: str = "push", path: str = WORKFLOW_PATH, created_at: str = "2026-11-16T10:00:00Z") -> dict[str, Any]:
    return {"id": int(rid), "head_sha": head, "status": status, "conclusion": conclusion, "event": event, "path": path,
            "html_url": f"https://github.com/{repo}/actions/runs/{rid}", "created_at": created_at,
            "repository": {"full_name": repo}}


def make_client(cwd: str | None = None) -> GithubClient:
    return RealGithubClient(cwd)


def _run_repo(run: dict[str, Any]) -> str:
    return str((run.get("repository") or {}).get("full_name") or "")


def judge(ref: str | None, head: str | None, client: GithubClient | None = None) -> tuple[str, str]:
    """(state, detail) for a `gh-run:<id>` ref against `head` (full sha). Never raises."""
    ref = (ref or "").strip()
    m = REF_RE.match(ref)
    if not m:
        return INVALID, f"{ref[:60]!r} is not a gh-run:<numeric run id> ref"
    if not head or not _FULL_SHA.match(head):
        return INVALID, "judging a gh-run needs the head's FULL sha"
    try:
        client = client or make_client()
        run = client.run(m.group(1))
        repo = client.repo()
    except CiVerdictError as exc:
        return INVALID, f"cannot read {ref} from GitHub: {exc}"
    except Exception as exc:  # noqa: BLE001 - unmeasurable is reported, never green
        return INVALID, f"UNMEASURED ({type(exc).__name__}: {str(exc)[:160]})"
    if not run:
        return INVALID, f"{ref} not found on GitHub"
    url = run.get("html_url") or ref
    if _run_repo(run) and _run_repo(run).lower() != repo.lower():
        return INVALID, f"{ref} belongs to {_run_repo(run)}, not {repo}"
    if str(run.get("path") or "") != WORKFLOW_PATH:
        return INVALID, f"{ref} is workflow {run.get('path')!r}, not {WORKFLOW_PATH}"
    if run.get("head_sha") != head:
        return INVALID, f"{ref} judged {str(run.get('head_sha'))[:9]}, not {head[:9]} (full-sha match required): {url}"
    if run.get("status") != "completed":
        return PENDING, f"{PENDING_PREFIX} {url} ({run.get('status')})"
    if run.get("conclusion") == "success":
        return GREEN, f"{ref}: test.yml green on {head[:9]} ({url})"
    return RED, f"{ref}: test.yml {run.get('conclusion')} on {head[:9]} ({url})"


def find_existing(head: str, client: GithubClient) -> str | None:
    """Newest test.yml run (any trigger) on EXACTLY this head in this repo: prefer one that is not red-cancelled."""
    runs = [r for r in client.runs_for_head(head)
            if r.get("head_sha") == head and str(r.get("path") or WORKFLOW_PATH) == WORKFLOW_PATH
            and (not _run_repo(r) or _run_repo(r).lower() == client.repo().lower())]
    runs.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    for r in runs:  # an in-flight or green run beats a newer cancelled one
        if r.get("status") != "completed" or r.get("conclusion") == "success":
            return f"gh-run:{r['id']}"
    return f"gh-run:{runs[0]['id']}" if runs else None


def dispatch(branch: str, head: str, client: GithubClient, *, polls: int = 5, sleep: Callable[[float], None] = time.sleep,
             interval_s: float = 8.0) -> str:
    """Dispatch test.yml on `branch` (tip must equal `head`) and return the new run's `gh-run:<id>` (bounded poll)."""
    tip = client.branch_tip(branch)
    if tip != head:
        raise CiVerdictError(f"origin/{branch} is at {str(tip)[:9]}, not {head[:9]}: push the branch first "
                             "(a workflow dispatch runs the branch tip, not a sha)")
    before = {str(r["id"]) for r in client.runs_for_head(head)}
    client.dispatch(branch, client.merge_base(head))
    for i in range(polls):
        for r in client.runs_for_head(head):
            if str(r["id"]) not in before and r.get("event") == "workflow_dispatch":
                return f"gh-run:{r['id']}"
        if i < polls - 1:
            sleep(interval_s)
    raise CiVerdictError(f"dispatched test.yml on {branch} but no new run on {head[:9]} appeared; re-request shortly "
                         "(it will be found by head sha)")


def resolve_for_filing(branch: str, head: str, client: GithubClient | None = None, **kw: Any) -> dict[str, Any]:
    """find_existing else dispatch, then judge. {ok, ref, state, detail, dispatched}; ok False carries `error`."""
    try:
        client = client or make_client()
        ensure = getattr(client, "ensure_quota", None)
        start = int(ensure()["remaining"]) if ensure else None
        ref, dispatched = find_existing(head, client), False
        if ref is None:
            ref, dispatched = dispatch(branch, head, client, **kw), True
    except CiVerdictError as exc:
        return {"ok": False, "error": f"GitHub CI verdict unavailable: {exc}"}
    state, detail = judge(ref, head, client)
    return {"ok": True, "ref": ref, "state": state, "detail": detail, "dispatched": dispatched,
            "api_calls": getattr(client, "api_calls", None), "rate_remaining_start": start,
            "rate_remaining": getattr(client, "rate_remaining", None)}
