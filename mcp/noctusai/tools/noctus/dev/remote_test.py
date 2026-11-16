"""remote_test: a heavy TEST run goes to a GitHub Actions runner by construction; the laptop slot is the fallback.

WHY (2026-11-16, owner's top priority): the laptop's single heavy slot is shared by ~10 Claude sessions, so runs wait
hours, swap fills up and the harness kills runs for low memory. The same suites run on GitHub. `hw_admission.py run`
(the one entry every heavy command already goes through: engineers by brief, bare commands by the `heavy_run_guard`
rewrite) now asks `try_remote` first; only when that declines does the command take the local slot.

CONTRACT (same as a local run): the caller sees streamed progress on stderr, the test summary, and the EXACT exit
code of the test command. Unmeasurable is never a pass: a remote run that did not complete exits 75 (EX_TEMPFAIL),
the same code "not admitted" uses.

WHAT RUNS REMOTELY: exactly one test command (`pytest`, `python -m pytest`, `vitest`, `npx vitest`, `npm test`),
optionally behind a leading `cd <dir> &&`, from the same subdirectory, with the same args, at the PUSHED head sha, via
`.github/workflows/remote-test.yml`. The allowlist (`validate_argv`) is enforced here AND by the workflow itself (it
runs this file's `validate`/`exec` subcommands), so no arbitrary shell ever reaches a runner.

LOUD FALLBACKS to the local slot (a `REMOTE-TEST FALLBACK:` line naming the reason + a telemetry row): `--local` /
`NOCTUS_TEST_BACKEND=local`, a nested run that inherits a slot, an unparseable/compound command, env assignments (not
forwarded), a non-test runner (build/playwright), a detached HEAD, uncommitted changes (remote would test the pushed
sha, not the edits), an unpushed HEAD, `gh` missing/unauthenticated, the workflow missing on GitHub. With
`NOCTUS_TEST_BACKEND=remote` there is NO fallback: an unmet precondition exits 75 and runs nothing.

SEAMS, nothing patched: GitHub is `ci_verdict.RealGithubClient` (shells `gh`; tests put a real recorder `gh` on PATH);
the clock/sleep/output are parameters.

KB: PATTERNS/devops/hardware-admission-budget.md (remote-by-default) · PATTERNS/devops/merge-queue.md.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

WORKFLOW = "remote-test.yml"
ENV_BACKEND = "NOCTUS_TEST_BACKEND"
ENV_TIMEOUT = "NOCTUS_REMOTE_TEST_TIMEOUT_S"
DEFAULT_TIMEOUT_S = 3600.0
MARKER = "NOC-REMOTE-TEST-EXIT="
STEP_NAME = "Run test command"
EX_TEMPFAIL = 75
NOT_A_TEST = "not a test run"
MODES = ("auto", "remote", "local")
_BAD_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_WORKDIR_OK = re.compile(r"^[A-Za-z0-9_./-]*$")
_OPS = {"&&", "||", ";", "|", "&", "(", ")", "|&", ";;"}
_SHELLS = {"bash", "sh", "zsh"}
_TEST_KINDS = {"pytest", "vitest"}  # heavy_run_guard._heavy_kind results that are TEST runs (not build/playwright/whisper)


def _sibling(name: str):
    """Load a sibling module (works as a package member and when this file is run by path on a CI runner)."""
    mod = sys.modules.get(f"noc_{name}")
    if mod is not None:
        return mod
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"noc_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ── the allowlist (shared by the client and the workflow) ──────────────────────────────────────────────────────────


def validate_argv(argv: list[str]) -> str | None:
    """None when `argv` is an allowed test runner invocation, else the refusal reason."""
    if not argv:
        return "empty command"
    if any(_BAD_CHARS.search(a) for a in argv):
        return "control characters in an argument"
    cmd, rest = argv[0], argv[1:]
    if cmd in {"pytest", "py.test", "vitest"}:
        return None
    if cmd in {"python", "python3"}:
        return None if rest[:2] == ["-m", "pytest"] else "python is allowed only as `python -m pytest`"
    if cmd == "npx":
        return None if rest[:1] == ["vitest"] else "npx is allowed only as `npx vitest`"
    if cmd == "npm":
        return None if rest[:1] == ["test"] or rest[:2] == ["run", "test"] else "npm is allowed only as `npm test` / `npm run test`"
    return f"{cmd!r} is not an allowed test runner (pytest, python -m pytest, vitest, npx vitest, npm test)"


def validate_workdir(workdir: str) -> str | None:
    if workdir.startswith("/") or ".." in Path(workdir).parts or not _WORKDIR_OK.match(workdir):
        return f"workdir {workdir!r} must be a plain relative path inside the repository"
    return None


def runner_kind(argv: list[str]) -> str:
    """`node` for vitest/npx/npm runs, else `python` (which toolchain the runner sets up)."""
    return "node" if argv[0] in {"vitest", "npx", "npm"} else "python"


# ── turning a gated command into a remote plan ─────────────────────────────────────────────────────────────────────


@dataclass
class Plan:
    argv: list[str]
    workdir: str  # relative to the repository root
    top: str


def _git(cwd: str, *args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60, check=False)  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return r.returncode, r.stdout.strip()


def _tokens(script: str) -> list[str]:
    lex = shlex.shlex(script, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    return list(lex)


def plan_from_argv(argv: list[str], cwd: str) -> Plan | str:
    """A `Plan`, or the reason this command cannot go remote (always a sentence for the FALLBACK line)."""
    hrg = _sibling("heavy_run_guard")
    if len(argv) >= 3 and os.path.basename(argv[0]) in _SHELLS and argv[1] == "-c":
        try:
            toks = _tokens(argv[2])
        except ValueError as exc:
            return f"unparseable command ({exc})"
    else:
        toks = list(argv)
    target = cwd
    if toks[:1] == ["cd"] and len(toks) >= 3 and toks[2] == "&&":
        target = toks[1] if os.path.isabs(toks[1]) else os.path.join(cwd, toks[1])
        toks = toks[3:]
    if any(t in _OPS for t in toks):
        return "compound command (only one test command, optionally after `cd <dir> &&`, can go remote)"
    words, env = hrg._strip_prefix(toks)
    if env:
        return f"env assignment(s) {sorted(env)} are not forwarded to the runner"
    if not words:
        return "empty command"
    if any(a in hrg._BENIGN for a in words[1:]):
        return "nothing heavy runs (--collect-only/--help/--version)"
    kind = hrg._heavy_kind(words)
    if kind not in _TEST_KINDS:
        return f"{NOT_A_TEST} (classified {kind!r}); only pytest/vitest/npm test go remote"
    rc, top = _git(target, "rev-parse", "--show-toplevel")
    if rc != 0 or not top:
        return f"{target} is not inside a git repository"
    top_real, here = os.path.realpath(top), os.path.realpath(target)
    workdir = os.path.relpath(here, top_real)
    workdir = "" if workdir == "." else workdir
    if workdir.startswith(".."):
        return "the working directory is outside the repository"
    base = os.path.basename(words[0])
    norm = ["python" if re.fullmatch(r"python[\d.]*", base) else base, *words[1:]]
    out: list[str] = [norm[0]]
    for a in norm[1:]:
        if os.path.isabs(a):  # a path under the worktree is the same file on the runner, relative to the workdir
            ar = os.path.realpath(a)
            if not (ar == top_real or ar.startswith(top_real + os.sep)):
                return f"argument {a!r} is an absolute path outside the repository"
            a = os.path.relpath(ar, here)
        out.append(a)
    bad = validate_argv(out) or validate_workdir(workdir)
    return bad if bad else Plan(argv=out, workdir=workdir, top=top)


# ── log parsing ────────────────────────────────────────────────────────────────────────────────────────────────────

_LOG_LINE = re.compile(r"^(?P<job>[^\t]*)\t(?P<step>[^\t]*)\t(?:﻿)?\d{4}-\d\d-\d\dT[\d:.]+Z ?(?P<text>.*)$")


def parse_log(text: str) -> tuple[int | None, list[str]]:
    """(exit code the test command printed, that step's output lines) from `gh run view --log` text."""
    lines: list[str] = []
    code: int | None = None
    for raw in text.splitlines():
        m = _LOG_LINE.match(raw)
        if not m or m.group("step").strip() != STEP_NAME:
            continue
        body = m.group("text")
        if body.startswith(MARKER):
            tail = body[len(MARKER):].strip()
            code = int(tail) if tail.lstrip("-").isdigit() else code
        else:
            lines.append(body)
    return code, lines


def summarize(lines: list[str], tail: int = 15, failed_cap: int = 60) -> list[str]:
    """The pytest/vitest summary: from `short test summary info` when present (capped), else the last `tail` lines."""
    for i, ln in enumerate(lines):
        if "short test summary info" in ln:
            return lines[i:i + failed_cap]
    return lines[-tail:]


# ── the run ────────────────────────────────────────────────────────────────────────────────────────────────────────


def resolve_mode(flag: str | None = None) -> str:
    raw = (flag or os.environ.get(ENV_BACKEND) or "auto").strip().lower()
    if raw not in MODES:
        sys.stderr.write(f"REMOTE-TEST: {ENV_BACKEND}={raw!r} is not one of {MODES}; using auto\n")
        return "auto"
    return raw


def _timeout_s() -> float:
    try:
        return float(os.environ.get(ENV_TIMEOUT) or DEFAULT_TIMEOUT_S)
    except ValueError:
        return DEFAULT_TIMEOUT_S


def try_remote(job: str, argv: list[str], *, cwd: str, mode: str | None = None, client: Any = None,
               log: Callable[[dict[str, Any]], None] | None = None, err: Any = None,
               sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
               polls: int = 5, interval_s: float = 8.0) -> int | None:
    """Run `argv` on GitHub and return the test command's exit code; None = the caller runs it on the local slot.

    A fallback is never silent: it prints `REMOTE-TEST FALLBACK: <reason>` and logs a `remote_fallback` row.
    Under mode `remote` there is no fallback: the reason is printed and 75 is returned (nothing ran)."""
    err = err if err is not None else sys.stderr
    log = log or (lambda _row: None)
    mode = resolve_mode(mode)

    def say(msg: str) -> None:
        print(msg, file=err, flush=True)

    def decline(reason: str) -> int | None:
        log({"event": "remote_fallback", "backend": "local" if mode != "remote" else "refused", "job": job,
             "mode": mode, "reason": reason})
        if mode == "remote":
            say(f"REMOTE-TEST REFUSED ({ENV_BACKEND}=remote forbids a local fallback): {reason}. Nothing ran (exit {EX_TEMPFAIL}).")
            return EX_TEMPFAIL
        say(f"REMOTE-TEST FALLBACK: {reason}: running on the local slot")
        return None

    if mode == "local":
        say(f"REMOTE-TEST: local backend requested ({ENV_BACKEND}=local / --local): running on the local slot")
        log({"event": "remote_fallback", "backend": "local", "job": job, "mode": mode, "reason": "local requested"})
        return None
    if os.environ.get("NOCTUS_HW_SLOT_HELD"):
        return decline("nested inside a run that already holds a local slot")
    plan = plan_from_argv(argv, cwd)
    if isinstance(plan, str):
        # a build / playwright / any non-test command is local BY DESIGN, not a fallback: no noise, no row
        return None if plan.startswith(NOT_A_TEST) else decline(plan)
    rc, branch = _git(plan.top, "symbolic-ref", "--short", "-q", "HEAD")
    if rc != 0 or not branch:
        return decline("detached HEAD (a workflow runs a branch tip)")
    rc, head = _git(plan.top, "rev-parse", "HEAD")
    rc2, dirty = _git(plan.top, "status", "--porcelain")
    if rc != 0 or rc2 != 0:
        return decline("cannot read the git state")
    if dirty:
        return decline("working tree has uncommitted changes: a remote run tests the pushed sha, not those edits")
    ci = _sibling("ci_verdict")
    try:
        client = client or ci.make_client(plan.top)
        calls0 = getattr(client, "api_calls", 0)
        tip = client.remote_tip(branch)
        if tip != head:
            return decline(f"HEAD not pushed: origin/{branch} is at {str(tip)[:9]}, local HEAD {head[:9]} (push first)")
        try:  # free `gh api rate_limit`; below the floor -> RateLimited -> local slot (GitHub first, never stop work)
            rate_start: int | None = int(client.ensure_quota()["remaining"])
        except ci.RateLimited:
            raise
        except ci.CiVerdictError:
            rate_start = None  # an unreadable meter never blocks work (telemetry records None)
        if not client.workflow_exists(WORKFLOW):
            return decline(f"workflow {WORKFLOW} is missing on GitHub (it must exist on the default branch to be dispatchable)")
        before = {str(r["id"]) for r in client.runs_for_workflow(WORKFLOW, branch)}
        cmd = shlex.join(plan.argv)
        client.dispatch_workflow(WORKFLOW, branch, {"ref": branch, "sha": head, "workdir": plan.workdir or ".", "cmd": cmd})
        run: dict[str, Any] | None = None
        for i in range(polls):
            for r in client.runs_for_workflow(WORKFLOW, branch):
                if str(r["id"]) not in before and r.get("head_sha") == head:
                    run = r
                    break
            if run or i == polls - 1:
                break
            sleep(interval_s)
        if run is None:
            return decline(f"dispatched {WORKFLOW} but no new run on {head[:9]} appeared")
    except ci.RateLimited as exc:
        return decline(f"github-quota {exc.remaining}/5000 resets {ci.reset_clock(exc.reset_epoch)[:5]}Z ({exc})")
    except ci.CiVerdictError as exc:
        return decline(f"GitHub unavailable: {exc}")
    run_id, url = str(run["id"]), run.get("html_url") or str(run["id"])
    t0 = clock()
    say(f"REMOTE-TEST START job={job} backend=remote run={url} sha={head[:9]} workdir={plan.workdir or '.'} cmd={cmd}")
    def tel() -> dict[str, Any]:  # quota telemetry on every outcome row: what this run cost GitHub, and what was left
        return {"api_calls": getattr(client, "api_calls", 0) - calls0, "rate_remaining_start": rate_start,
                "rate_remaining_end": getattr(client, "rate_remaining", None)}

    row: dict[str, Any] = {"event": "remote_run", "backend": "remote", "job": job, "mode": mode, "run_id": run_id,
                           "run_url": url, "sha": head, "branch": branch, "workdir": plan.workdir or ".", "cmd": cmd}
    try:
        seen: set[str] = set()  # `gh run watch` redraws the whole table each interval: print only lines not seen yet

        def progress(ln: str) -> None:
            if ln not in seen:
                seen.add(ln)
                say(f"REMOTE-TEST ... {ln}")

        finished = client.watch(run_id, progress, _timeout_s(), sleep=sleep, clock=clock, on_quota="raise")
        if not finished:
            wall = round(clock() - t0, 1)
            log({**row, **tel(), "wall_s": wall, "outcome": {"exit_code": EX_TEMPFAIL, "conclusion": "timeout"}})
            say(f"REMOTE-TEST UNMEASURED: still running after {wall}s: {url} (read it later: {url}). Exit {EX_TEMPFAIL}.")
            return EX_TEMPFAIL
        final = client.run(run_id) or {}
        if final.get("head_sha") != head:  # verdict-channel integrity: the exit code must belong to THIS head
            wall = round(clock() - t0, 1)
            log({**row, **tel(), "wall_s": wall, "outcome": {"exit_code": EX_TEMPFAIL, "conclusion": "sha_mismatch"}})
            say(f"REMOTE-TEST UNMEASURED: run {run_id} judged {str(final.get('head_sha'))[:9]}, not local HEAD {head[:9]}. "
                f"Exit {EX_TEMPFAIL}.")
            return EX_TEMPFAIL
        code, lines = parse_log(client.run_log(run_id))
    except ci.RateLimited as exc:  # quota exhausted mid-watch: stop watching, run the SAME command on the local slot
        wall = round(clock() - t0, 1)
        log({**row, **tel(), "event": "remote_fallback", "backend": "local" if mode != "remote" else "refused",
             "reason": "github-quota-midwatch", "wall_s": wall, "orphaned_run_url": url})
        if mode == "remote":
            say(f"REMOTE-TEST REFUSED ({ENV_BACKEND}=remote forbids a local fallback): github-quota-midwatch ({exc}); "
                f"orphaned GitHub run: {url}. Exit {EX_TEMPFAIL}.")
            return EX_TEMPFAIL
        say(f"REMOTE-TEST FALLBACK: github-quota-midwatch ({exc}); orphaned GitHub run (read it later): {url}: running on the local slot")
        return None
    except ci.CiVerdictError as exc:
        wall = round(clock() - t0, 1)
        log({**row, **tel(), "wall_s": wall, "outcome": {"exit_code": EX_TEMPFAIL, "conclusion": "gh_error", "error": str(exc)[:200]}})
        say(f"REMOTE-TEST UNMEASURED: lost contact with GitHub ({exc}); the run may still finish: {url}. Exit {EX_TEMPFAIL}.")
        return EX_TEMPFAIL
    wall = round(clock() - t0, 1)
    conclusion = final.get("conclusion")
    for ln in summarize(lines):
        print(ln, flush=True)
    if code is None:
        log({**row, **tel(), "wall_s": wall, "outcome": {"exit_code": EX_TEMPFAIL, "conclusion": conclusion}})
        say(f"REMOTE-TEST UNMEASURED: run {conclusion} before the test command printed its exit code "
            f"(setup/validation failed, or cancelled): {url}. Exit {EX_TEMPFAIL}.")
        return EX_TEMPFAIL
    log({**row, **tel(), "wall_s": wall, "outcome": {"exit_code": code, "conclusion": conclusion}})
    say(f"HW-RUN DONE rc={code} elapsed={int(wall)}s backend=remote run={url} sha={head[:9]}")
    return code


# ── the runner side (stdlib only; `.github/workflows/remote-test.yml` calls these) ─────────────────────────────────


def _runner_inputs() -> tuple[list[str], str]:
    argv = shlex.split(os.environ.get("CMD", ""))
    return argv, os.environ.get("WORKDIR", "") or "."


def runner_validate() -> int:
    argv, workdir = _runner_inputs()
    why = validate_argv(argv) or validate_workdir(workdir)
    if why:
        print(f"::error::remote-test refused the command: {why}")
        return 2
    if not (Path(workdir) / ".").is_dir():
        print(f"::error::workdir {workdir!r} does not exist at this sha")
        return 2
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"kind={runner_kind(argv)}\n")
    print(f"validated: kind={runner_kind(argv)} workdir={workdir} argv={argv}")
    return 0


def runner_exec() -> int:
    argv, workdir = _runner_inputs()
    why = validate_argv(argv) or validate_workdir(workdir)
    if why:  # defense in depth: the validate step already ran
        print(f"::error::remote-test refused the command: {why}")
        return 2
    sys.stdout.flush()
    rc = subprocess.run(argv, cwd=workdir, check=False).returncode  # noqa: S603 - argv list, allowlisted, no shell
    print(f"{MARKER}{rc}", flush=True)
    return rc


if __name__ == "__main__":  # pragma: no cover - thin runner entry
    sub = sys.argv[1] if len(sys.argv) > 1 else ""
    if sub not in {"validate", "exec"}:
        sys.exit("usage: remote_test.py validate|exec  (reads CMD and WORKDIR from the environment)")
    sys.exit(runner_validate() if sub == "validate" else runner_exec())
