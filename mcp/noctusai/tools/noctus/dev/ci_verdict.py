"""ci_verdict: delivery-contract item 5 judged by a GitHub Actions `test.yml` run, not a local machine run.

WHY (2026-11-16): the local CI-parity run needs a machine-wide heavy slot on an 8 GB laptop shared by many sessions;
filings came back UNMEASURED or timed out. The same suites run on GitHub, so item 5 now accepts `gh-run:<databaseId>`.

NOT forgeable: `judge` resolves the id against GitHub (repo from `git remote get-url origin`, workflow path, full head
sha, status/conclusion) - a string a caller typed proves nothing. The GitHub access is a seam (`GithubClient`:
Real shells `gh`, Fake for tests, `make_client` factory); no module function is ever patched.

KB: PATTERNS/devops/release-steward.md (item 5).
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
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

    def _gh(self, *args: str) -> Any:
        rc, out, err = self._sh(["gh", *args], self.cwd)
        if rc != 0:
            raise CiVerdictError(f"gh {' '.join(args[:2])} failed (rc={rc}): {(err or out).strip()[-300:]} "
                                 "(is `gh auth status` green?)")
        return json.loads(out) if out.strip() else None

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
        # scope=changed (2026-11-17): a branch verdict is scoped to its diff against base/merge-base.
        args = ["workflow", "run", WORKFLOW_FILE, "--ref", branch, "-R", self.repo(), "-f", "scope=changed"]
        if base:
            args += ["-f", f"base={base}"]
        rc, out, err = self._sh(["gh", *args], self.cwd)
        if rc != 0:
            raise CiVerdictError(f"gh workflow run failed (rc={rc}): {(err or out).strip()[-300:]}")


    def remote_tip(self, branch: str) -> str | None:
        """The AUTHORITATIVE pushed tip (`git ls-remote`), not the possibly stale local origin/<branch> ref."""
        rc, out, _e = self._sh(["git", "ls-remote", "origin", f"refs/heads/{branch}"], self.cwd)
        return (out.split() or [None])[0] if rc == 0 else None

    def workflow_exists(self, workflow: str) -> bool:
        rc, out, err = self._sh(["gh", "api", f"repos/{self.repo()}/actions/workflows/{workflow}"], self.cwd)
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
        rc, out, err = self._sh(["gh", *args], self.cwd)
        if rc != 0:
            raise CiVerdictError(f"gh workflow run {workflow} failed (rc={rc}): {(err or out).strip()[-300:]}")

    def runs_for_workflow(self, workflow: str, branch: str) -> list[dict[str, Any]]:
        d = self._gh("api", f"repos/{self.repo()}/actions/workflows/{workflow}/runs"
                            f"?branch={branch}&event=workflow_dispatch&per_page=30")
        return list((d or {}).get("workflow_runs") or [])

    def watch(self, run_id: str, out: Callable[[str], None], timeout_s: float) -> bool:
        """ONE blocking `gh run watch`, progress lines to `out`; False when `timeout_s` elapsed first."""
        proc = subprocess.Popen(["gh", "run", "watch", str(run_id), "-R", self.repo(), "--interval", "15"],  # noqa: S603
                                cwd=self.cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        timer = threading.Timer(timeout_s, proc.kill)
        timer.start()
        try:
            for line in proc.stdout or []:
                if line.strip():
                    out(line.rstrip("\n"))
            proc.wait()
        finally:
            timer.cancel()
        return proc.returncode is not None and proc.returncode >= 0

    def run_log(self, run_id: str) -> str:
        rc, out, err = self._sh(["gh", "run", "view", str(run_id), "--log", "-R", self.repo()], self.cwd, timeout=300)
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
        return self.runs.get(str(run_id))

    def runs_for_head(self, head: str) -> list[dict[str, Any]]:
        self.repo()
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


def dispatch(branch: str, head: str, client: GithubClient, *, polls: int = 6, sleep: Callable[[float], None] = time.sleep,
             interval_s: float = 4.0) -> str:
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
        ref, dispatched = find_existing(head, client), False
        if ref is None:
            ref, dispatched = dispatch(branch, head, client, **kw), True
    except CiVerdictError as exc:
        return {"ok": False, "error": f"GitHub CI verdict unavailable: {exc}"}
    state, detail = judge(ref, head, client)
    return {"ok": True, "ref": ref, "state": state, "detail": detail, "dispatched": dispatched}
