"""``noctus.dev.toolkit_freshness`` — detect a stale MCP server process.

The incident (2026-09-18)
    ``mcp/noctusai`` is imported once, into ``sys.modules``, by a long-lived
    server process. Python does not re-read a module's file after that —
    editing ``task_branch.py`` on disk does nothing to the code already
    resident in memory. The server that ran this session had been up since
    2026-09-16 18:45; ``task_branch.py`` was last modified 2026-09-18 01:15.
    For ~30 hours every ``noctus.dev.*`` call — including ``predeploy_check``,
    ``deploy_verify``, ``spa_smoke``, ``migrate_product`` and ``task_branch``
    itself — executed two-day-old code, and nothing anywhere surfaced that.
    Concretely: ``task_branch action=start`` silently stopped provisioning
    worktrees (``wire_env`` didn't exist yet in the loaded code), so every
    worktree created that day lacked ``.env`` / ``node_modules``, which then
    made colocated tests fail in a way an engineer reasonably (and wrongly)
    called "pre-existing."

The rule this operationalizes
    `KB § PATTERNS/common/methodology-execution-discipline.md` § 6
    ("verdict-channel integrity") says the exit code you read must belong to
    what you are judging. A stale interpreter is that rule ONE LEVEL UP: the
    CODE you are judging must be the code on disk. No amount of care reading
    a tool's return value helps when the process answering was never asked
    the current question.

Design
    1. ``capture_baseline()`` — called exactly once, by
       ``tools/__init__.py::register_all`` right after every tool umbrella
       (google/llm/noctus/kb_sync — the full ``mcp/noctusai`` module graph)
       has finished importing. Walks ``sys.modules`` for every module whose
       ``__file__`` resolves under this toolkit's root, stats it, and
       freezes ``{path: (mtime, size)}`` as the answer to "what did this
       process actually load, and when." Idempotent — a second call is a
       no-op unless ``force=True`` (tests use ``force=True`` to re-baseline
       against a tmp tree).
    2. ``check()`` — re-stats every baselined file and reports drift: a
       changed mtime/size, or a file that no longer exists. TTL-cached
       (default 5s) so a burst of tool calls costs one stat pass, not one
       per call — see the module docstring's cost numbers in
       ``mcp/noctusai/tests/test_toolkit_freshness.py``.
    3. ``warn_if_stale`` / ``refuse_gate`` — the two postures a high-stakes
       tool can take when ``check()`` comes back stale. See their
       docstrings for the refuse-vs-warn line this repo drew.

What this deliberately does NOT do
    Hot-reload IN THIS PROCESS. Swapping code under a live module graph
    mid-call is a much worse failure mode than reporting staleness — the
    remedy for the SERVER's own staleness is always "restart it" (``/mcp``
    in Claude Code), never a live patch. R4 (below) works around the
    SYMPTOM (a blocked caller) without touching this invariant: it launches
    an entirely NEW process rather than patching the old one.

R4 — the fresh-subprocess fallback (2026-09-24, release-no-freeze)
    The 2026-09-18 incident's fix (above) traded one failure mode for
    another: every gated ``confirm=True`` write on a stale server now hard-
    REFUSED, which is safe but forced a manual ``/mcp`` reconnect before the
    caller's actual work could proceed — losing hours of otherwise-idle
    agent time whenever a peer session's own edit made the shared server's
    module graph stale mid-task.

    ``refuse_gate`` no longer refuses a stale write outright. It re-runs the
    SAME call as ``python mcp/noctusai/cli.py --<tool-flag> ...`` in a
    brand-new subprocess (``_run_via_fresh_subprocess``) — a subprocess
    re-imports ``mcp/noctusai/**`` from disk on launch, so it can never
    itself be "the stale process." The subprocess's own JSON result is
    returned verbatim, plus ``executed_via: "fresh_subprocess"``. Never
    silent: the result also carries a ``warnings`` entry naming what
    happened and still recommending a server restart (the subprocess is a
    one-call bridge, not a substitute for fixing the underlying staleness).

    Scope, by construction:
      - Only WRITE calls (``is_write`` — the same predicate `refuse_gate`
        already used to decide refuse-vs-warn) ever reach this path. A
        ``confirm=False`` preview stays in-process (WARN posture,
        unaffected) — the cheap path was never the problem.
      - ``allow_stale_toolkit=True`` still means "I've manually verified
        THIS process's in-memory behaviour is safe" — it takes the OLD
        in-process path, never the subprocess. The two escape hatches are
        for different trust levels and must never be conflated.
      - A tool with no wired CLI mapping (``_tool_cli_argv`` returns
        ``None``) or a genuine PRE-LAUNCH failure (the child process never
        started — e.g. the interpreter itself could not be exec'd) falls
        back to the ORIGINAL hard refusal (nothing was touched, so "refused"
        is still accurate). A POST-LAUNCH failure (timeout, unparseable
        output) is NEVER reported as a refusal — the child may have started
        a real write before dying; see ``status='fresh_subprocess_outcome_
        unknown'`` below.
      - ``_extract_trailing_json`` exists because ``cli.py`` could emit INFO
        log lines on stdout BEFORE its final ``json.dumps(...)`` — a naive
        whole-blob parse broke on "Extra data" (found wiring this very
        fallback, 2026-09-24). FIXED AT THE ROOT the same day: ``cli.py``
        now configures its logging via ``auto_configure_for_cli(...,
        use_stderr=True)`` and its startup banner prints to ``sys.stderr``
        — stdout is pure JSON on every dispatch path. The scan is kept as a
        defense-in-depth belt (a future flag could still print something
        stray) even though it is no longer load-bearing for this toolkit's
        own dispatch paths.
"""
from __future__ import annotations

import functools
import inspect
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

# .../mcp/noctusai/tools/noctus/dev/toolkit_freshness.py -> parents[3] == mcp/noctusai
TOOLKIT_ROOT: Path = Path(__file__).resolve().parents[3]

REMEDY = "Restart the MCP server (Claude Code: run `/mcp`) so it re-imports mcp/noctusai/** from disk."

# R4 (release-no-freeze, 2026-09-24): the 2026-09-18 incident's OTHER cost —
# every confirm=True gated write on a stale primary server used to hard-
# REFUSE, forcing a manual `/mcp` reconnect before the caller's actual work
# could proceed. A stale VERDICT is never trustworthy, but the CODE ON DISK
# right now is — so instead of refusing outright, `refuse_gate` re-execs the
# SAME call as `python mcp/noctusai/cli.py --<tool-flag> ...` in a brand-new
# subprocess (which re-imports everything fresh; it can never itself be
# "the stale process"), and returns THAT result with `executed_via:
# "fresh_subprocess"`. Read-only / confirm=False calls are UNAFFECTED — they
# stay in-process (WARN posture), per `refuse_gate`'s existing contract.
# F2 (compliance review, 2026-09-24): 600s was too tight for a genuinely
# slow write (e.g. `task_branch action='start'` symlinking ~18,840 entries,
# or a large migration set) — and killing the child on timeout is the worst
# possible outcome if it was mid-write. Raised substantially so a timeout is
# a rare, real "something is actually stuck" signal, not a routine hazard;
# `_run_via_fresh_subprocess` additionally NEVER treats a timeout as
# evidence nothing happened (see `status='fresh_subprocess_outcome_unknown'`).
_FRESH_SUBPROCESS_TIMEOUT_S = 1800.0

# F2: the read-only/dry-run verification step named in an "outcome unknown"
# result — the caller's next move to find out what actually happened.
_VERIFICATION_STEP: dict[str, str] = {
    "release": "noctus.dev.release stage='status' (read-only) to see the current chain state",
    "migrate_product": "noctus.dev.migrate_product confirm=False (dry-run) to see what's actually pending vs. applied",
    "deploy_image": "noctus.dev.deploy_verify — the INDEPENDENT witness, zero dependency on deploy_image having run",
    "task_branch": "noctus.dev.task_branch action='status' (read-only) to see the current worktree/branch state",
}

_TAIL_CHARS = 4000

_DEFAULT_TTL_SECONDS = 5.0

# ── baseline state (module-level; one process, one baseline) ───────────────
_baseline: dict[str, tuple[float, int]] | None = None
_loaded_at: float | None = None

# ── TTL-cached verdict ───────────────────────────────────────────────────
_cached_verdict: dict[str, Any] | None = None
_cached_at: float = 0.0


def _loaded_toolkit_files() -> dict[str, Path]:
    """{module_name: resolved_path} for every currently-loaded module whose
    ``__file__`` resolves under ``TOOLKIT_ROOT``. Reads ``sys.modules``
    directly rather than walking the filesystem — this answers "what did
    the process actually load" not "what exists on disk", which is the
    whole point (a file that exists but was never imported cannot be
    stale-in-memory)."""
    out: dict[str, Path] = {}
    root_str = str(TOOLKIT_ROOT)
    for name, mod in list(sys.modules.items()):
        file = getattr(mod, "__file__", None)
        if not file:
            continue
        try:
            path = Path(file).resolve()
        except OSError:
            continue
        path_str = str(path)
        if path_str == root_str or path_str.startswith(root_str + "/"):
            out[name] = path
    return out


def capture_baseline(force: bool = False) -> dict[str, Any]:
    """Freeze ``{path: (mtime, size)}`` for every currently-loaded toolkit
    module. Idempotent unless ``force=True``. Call once, after the server
    has finished importing every tool umbrella — see module docstring."""
    global _baseline, _loaded_at
    if _baseline is not None and not force:
        return {
            "ok": True,
            "status": "already_captured",
            "loaded_at": _loaded_at,
            "file_count": len(_baseline),
        }

    baseline: dict[str, tuple[float, int]] = {}
    for path in _loaded_toolkit_files().values():
        try:
            st = path.stat()
        except OSError:
            continue
        baseline[str(path)] = (st.st_mtime, st.st_size)

    _baseline = baseline
    _loaded_at = time.time()
    _invalidate_cache()
    return {
        "ok": True,
        "status": "captured",
        "loaded_at": _loaded_at,
        "file_count": len(baseline),
    }


def _invalidate_cache() -> None:
    global _cached_verdict, _cached_at
    _cached_verdict = None
    _cached_at = 0.0


def _compute_verdict() -> dict[str, Any]:
    """The uncached stat pass: baseline vs. current disk state."""
    if _baseline is None:
        capture_baseline()
    baseline = _baseline or {}

    changed: list[dict[str, Any]] = []
    deleted: list[str] = []

    for path_str, (mtime, size) in baseline.items():
        path = Path(path_str)
        try:
            st = path.stat()
        except OSError:
            deleted.append(path_str)
            continue
        if st.st_mtime != mtime or st.st_size != size:
            changed.append(
                {
                    "path": path_str,
                    "loaded_mtime": mtime,
                    "current_mtime": st.st_mtime,
                    "loaded_size": size,
                    "current_size": st.st_size,
                }
            )

    stale = bool(changed) or bool(deleted)
    return {
        "status": "stale" if stale else "fresh",
        "changed_files": changed,
        "deleted_files": deleted,
        "loaded_at": _loaded_at,
        "checked_files": len(baseline),
        "remedy": REMEDY if stale else None,
    }


def check(ttl_seconds: float = _DEFAULT_TTL_SECONDS, bypass_cache: bool = False) -> dict[str, Any]:
    """Return the freshness verdict. Cached with a TTL so a burst of tool
    calls in the same process does at most one stat pass per
    ``ttl_seconds`` window (see the module docstring's cost claim + the
    colocated test that measures it). ``bypass_cache=True`` forces a real
    stat pass right now — the explicit ``noctus.dev.toolkit_freshness``
    tool uses this, because a user asking "is it fresh, right now" should
    never get a several-second-old cached answer."""
    global _cached_verdict, _cached_at
    now = time.monotonic()
    if not bypass_cache and _cached_verdict is not None and (now - _cached_at) < ttl_seconds:
        result = dict(_cached_verdict)
        result["from_cache"] = True
        return result

    t0 = time.perf_counter()
    verdict = _compute_verdict()
    verdict["check_duration_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    verdict["from_cache"] = False
    _cached_verdict = verdict
    _cached_at = now
    return dict(verdict)


def stale_warning_message(verdict: dict[str, Any]) -> str:
    n_changed = len(verdict.get("changed_files", []))
    n_deleted = len(verdict.get("deleted_files", []))
    loaded_at = verdict.get("loaded_at")
    return (
        f"toolkit_stale: this MCP server's mcp/noctusai module graph is stale "
        f"vs. disk ({n_changed} file(s) changed, {n_deleted} deleted since it "
        f"loaded at {loaded_at}) — its answer may reflect code that no longer "
        f"exists on disk. Remedy: {REMEDY}"
    )


def refusal_payload(tool_name: str, verdict: dict[str, Any], allow_stale_toolkit: bool) -> dict[str, Any]:
    """The ``status='refused_stale_toolkit'`` shape — mirrors
    ``migrate_product``'s ``refused_stale_tree`` vocabulary/shape on
    purpose (same family of fail-closed refusal already established in
    this codebase)."""
    return {
        "ok": False,
        "status": "refused_stale_toolkit",
        "exit_code": 1,
        "toolkit_stale": True,
        "toolkit_freshness": verdict,
        "allow_stale_toolkit": allow_stale_toolkit,
        "warnings": [stale_warning_message(verdict)],
        "error": (
            f"{tool_name} refused to act: this MCP server's mcp/noctusai module "
            f"graph is stale vs. disk "
            f"({len(verdict.get('changed_files', []))} file(s) changed, "
            f"{len(verdict.get('deleted_files', []))} deleted since it was "
            f"loaded at {verdict.get('loaded_at')}) — acting on stale logic "
            f"against production is the case that actually hurts. "
            f"Remedy: {REMEDY} If you have manually verified this tool's "
            f"current in-memory behaviour is safe, pass "
            f"allow_stale_toolkit=True (almost always wrong)."
        ),
    }


def warn_if_stale(result: dict[str, Any], ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> dict[str, Any]:
    """Mutate + return ``result`` with a ``toolkit_stale`` bool that ALWAYS
    rides on the return (never silently omitted — `KB §
    01-PHILOSOPHY.md` no-silent-errors), and — only when actually stale —
    a loud ``warnings`` entry naming the remedy. For the WARN posture: the
    tool still answers (it's read-only or its mutation is dev-scoped and
    recoverable), but never as if it were current."""
    verdict = check(ttl_seconds=ttl_seconds)
    result["toolkit_stale"] = verdict["status"] == "stale"
    if result["toolkit_stale"]:
        result.setdefault("warnings", [])
        result["warnings"].append(stale_warning_message(verdict))
        result["toolkit_freshness"] = verdict
    return result


def warn_gate(tool_name: str, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> Callable:
    """Decorator for the WARN posture (read-only probes / dev-scoped,
    recoverable mutation): ``predeploy_check``, ``deploy_verify``,
    ``spa_smoke``, ``task_branch``. Runs the wrapped tool normally, then
    injects the freshness verdict into its dict result."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            if isinstance(result, dict):
                warn_if_stale(result, ttl_seconds=ttl_seconds)
            return result

        return wrapper

    return decorator


# ── R4: fresh-subprocess CLI argv mapping ───────────────────────────────────
# One entry per `refuse_gate`-wrapped tool, mirroring that tool's MCP-facing
# `register()` wrapper signature 1:1 (never the full inner-function surface —
# DI-only test seams like `run=`/`git_runner=`/`executor=` are neither
# MCP-exposed nor CLI-relevant). Adding a NEW `refuse_gate` consumer without
# adding it here is caught, not silently guessed at — see
# `_run_via_fresh_subprocess`'s "no CLI entry wired" hard-refusal below.
#
# `--flag=value` (F3, compliance review 2026-09-24), never a bare `value` as
# its own argv element: a value that itself starts with `-` (a sha, a slug,
# a free-text brief) passed as TWO argv elements — `["--release-sha", "-abc"]`
# — would have argparse read `-abc` as an unrecognized FLAG, not `--release-
# sha`'s value. `--flag=value` is unambiguous regardless of the value's
# content.
def _tool_cli_argv(tool_name: str, kwargs: dict[str, Any]) -> list[str] | None:
    """CLI argv (everything after ``cli.py``) for a gated write tool's bound
    kwargs. Returns ``None`` when `tool_name` has no wired entry."""
    if tool_name == "release":
        argv = [f"--release={kwargs.get('stage') or 'status'}"]
        if kwargs.get("confirm"):
            argv.append("--release-confirm")
        if kwargs.get("sha"):
            argv.append(f"--release-sha={kwargs['sha']}")
        mode = kwargs.get("mode") or "ff"
        if mode != "ff":
            argv.append(f"--release-mode={mode}")
        if kwargs.get("release_branch"):
            argv.append(f"--release-branch={kwargs['release_branch']}")
        return argv

    if tool_name == "migrate_product":
        product = kwargs.get("product")
        if not product:
            return None
        argv = [f"--migrate-product={product}"]
        if kwargs.get("confirm"):
            argv.append("--migrate-product-confirm")
        if kwargs.get("target"):
            argv.append(f"--migrate-product-target={kwargs['target']}")
        if kwargs.get("sha"):
            argv.append(f"--migrate-product-sha={kwargs['sha']}")
        if kwargs.get("project_ref"):
            argv.append(f"--migrate-product-project-ref={kwargs['project_ref']}")
        if kwargs.get("schema"):
            argv.append(f"--migrate-product-schema={kwargs['schema']}")
        if kwargs.get("worktree_path"):
            argv.append(f"--migrate-product-worktree-path={kwargs['worktree_path']}")
        if kwargs.get("allow_stale_tree"):
            argv.append("--migrate-product-allow-stale-tree")
        if kwargs.get("allow_inactive"):
            argv.append("--migrate-product-allow-inactive")
        return argv

    if tool_name == "deploy_image":
        product = kwargs.get("product")
        if not product:
            return None
        argv = [f"--deploy-image={product}"]
        if kwargs.get("confirm"):
            argv.append("--deploy-image-confirm")
        tag = kwargs.get("tag") or "latest"
        if tag != "latest":
            argv.append(f"--deploy-image-tag={tag}")
        source = kwargs.get("source") or "pull"
        if source != "pull":
            argv.append(f"--deploy-image-source={source}")
        ssh_host = kwargs.get("ssh_host") or "noctus-vps"
        if ssh_host != "noctus-vps":
            argv.append(f"--deploy-host={ssh_host}")
        if kwargs.get("skip_ancestry_check"):
            argv.append("--deploy-image-skip-ancestry-check")
        if kwargs.get("allow_inactive"):
            argv.append("--deploy-image-allow-inactive")
        return argv

    if tool_name == "task_branch":
        argv = [f"--task-branch={kwargs.get('action') or 'status'}"]
        if kwargs.get("slug"):
            argv.append(f"--task-branch-slug={kwargs['slug']}")
        if kwargs.get("confirm"):
            argv.append("--task-branch-confirm")
        if kwargs.get("project"):
            argv.append(f"--task-branch-project={kwargs['project']}")
        if kwargs.get("brief"):
            argv.append(f"--task-branch-brief={kwargs['brief']}")
        if kwargs.get("paths"):
            argv.append(f"--task-branch-paths={','.join(str(p) for p in kwargs['paths'])}")
        if kwargs.get("agent"):
            argv.append(f"--task-branch-agent={kwargs['agent']}")
        if kwargs.get("role"):
            argv.append(f"--task-branch-role={kwargs['role']}")
        if kwargs.get("parent"):
            argv.append(f"--task-branch-parent={kwargs['parent']}")
        if kwargs.get("wire_env") is False:
            argv.append("--task-branch-no-wire-env")
        if kwargs.get("verbose"):
            argv.append("--task-branch-verbose")
        return argv

    return None


# F3: the EXACT bound-argument names `_tool_cli_argv` reads for each tool —
# MUST mirror the `.get(...)`/membership checks above 1:1. Anything OUTSIDE
# this set (`remote`/`main_branch`/`prod_branch`/`run`/`executor`/
# `git_runner`/`consent_rows`/... — DI-only test seams, or a real knob that
# simply has no CLI flag yet) has NO way to reach the child process. Passing
# a NON-DEFAULT value for one of those and silently proceeding to subprocess
# anyway would run the child against the WRONG target (wrong remote, wrong
# executor, ...) with no signal at all — `_unmapped_param_diffs` catches
# that BEFORE any subprocess is launched.
_MAPPED_PARAMS: dict[str, frozenset[str]] = {
    "release": frozenset({"stage", "confirm", "sha", "mode", "release_branch"}),
    "migrate_product": frozenset({
        "product", "confirm", "target", "sha", "project_ref", "schema",
        "worktree_path", "allow_stale_tree", "allow_inactive",
    }),
    "deploy_image": frozenset({
        "product", "confirm", "tag", "source", "ssh_host",
        "skip_ancestry_check", "allow_inactive",
    }),
    "task_branch": frozenset({
        "action", "slug", "confirm", "project", "brief", "paths", "agent",
        "role", "parent", "wire_env", "verbose",
    }),
}


def _unmapped_param_diffs(
    tool_name: str, fn_sig: "inspect.Signature | None", bound_args: dict[str, Any],
) -> list[str]:
    """Names of bound args NOT in ``_MAPPED_PARAMS[tool_name]`` whose value
    differs from that parameter's OWN default — each one is a value the
    fresh-subprocess hop would SILENTLY DROP. A parameter with no default
    at all (should never happen for anything outside the mapped set, given
    today's signatures — defensive) is conservatively treated as always a
    diff rather than risk a false negative."""
    if fn_sig is None:
        return []
    mapped = _MAPPED_PARAMS.get(tool_name, frozenset())
    diffs: list[str] = []
    for name, value in bound_args.items():
        if name in mapped:
            continue
        param = fn_sig.parameters.get(name)
        if param is None:
            continue  # not a real parameter of this signature — ignore
        if param.default is inspect.Parameter.empty:
            diffs.append(name)
            continue
        if value != param.default:
            diffs.append(name)
    return diffs


def _extract_trailing_json(text: str) -> dict[str, Any] | None:
    """``cli.py``'s dispatch blocks all end with ``print(json.dumps(r,
    indent=2, default=str))`` as their LAST stdout write — but the same
    process can ALSO have logged INFO lines to stdout earlier (env_bootstrap,
    the toolkit banner) NOT captured on stderr, so a naive ``json.loads(out)``
    on the whole blob breaks on "Extra data" (2026-09-24, found wiring this
    very fallback). ``json.dumps(..., indent=2)`` always puts the TOP-LEVEL
    dict's opening brace alone on its own line at COLUMN 0 (no leading
    whitespace) — every OTHER ``{`` (a nested dict, e.g. inside a
    list-of-dicts value like a rider manifest's ``commits``) is indented, so
    an EXACT (non-stripped) ``"{"`` match is what distinguishes them —
    stripping first would wrongly match the LAST nested dict's brace instead
    of the true top-level one. Scan backward for the last column-0 ``{``
    line and parse from there to EOF. Returns ``None`` (never raises) on no
    match or a parse failure — the caller treats that as "unparseable"."""
    lines = text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i] == "{":
            blob = "\n".join(lines[i:])
            try:
                parsed = json.loads(blob)
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None


def _tail(text: str | None, n: int = _TAIL_CHARS) -> str:
    text = text or ""
    return text[-n:] if len(text) > n else text


def _outcome_unknown_payload(
    tool_name: str, cmd: list[str], *, rc: int | None, out: str, err: str, reason: str,
) -> dict[str, Any]:
    """F2 (compliance review, 2026-09-24): the ONLY honest shape for a
    POST-LAUNCH failure. The child process was actually started — for a
    write tool that means it may have already begun (or finished) a real
    mutation before we lost the ability to read its answer. Calling this
    'refused' would be a LIE (a refusal by definition means nothing was
    touched); `refused_stale_toolkit`/`refusal_payload` must never be
    reused here. `verification_step` is the caller's next move — a
    read-only probe that tells them what actually happened."""
    verify = _VERIFICATION_STEP.get(
        tool_name, "re-run the read-only status/dry-run form of this tool"
    )
    return {
        "ok": False,
        "status": "fresh_subprocess_outcome_unknown",
        "exit_code": 1,
        "executed_via": "fresh_subprocess",
        "tool": tool_name,
        "cmd": cmd,
        "rc": rc,
        "stdout_tail": _tail(out),
        "stderr_tail": _tail(err),
        "verification_step": verify,
        "error": (
            f"{tool_name}: the fresh subprocess was LAUNCHED — it may have "
            f"started (or completed) a real action — but its outcome could "
            f"not be determined ({reason}). This is NOT a refusal: do not "
            f"treat it as 'nothing happened'. Verify with: {verify}."
        ),
    }


def _run_via_fresh_subprocess(
    tool_name: str,
    kwargs: dict[str, Any],
    verdict: dict[str, Any],
    allow_stale_toolkit: bool,
    subprocess_run: Callable[..., tuple[int, str, str]] | None = None,
    fn_sig: "inspect.Signature | None" = None,
) -> dict[str, Any]:
    """The R4 fallback: instead of refusing a confirm=True write outright
    because THIS process's module graph is stale, run the SAME call as
    ``python mcp/noctusai/cli.py --<tool-flag> ...`` in a brand-new
    subprocess — which re-imports ``mcp/noctusai/**`` from disk, so it can
    never itself be the stale process. Returns the subprocess's own JSON
    result with ``executed_via: "fresh_subprocess"`` added; ``toolkit_stale``
    rides through UNCHANGED from whatever the subprocess itself reports
    (almost always ``False`` — a process that just launched has nothing to
    have drifted from).

    F2 (compliance review, 2026-09-24) drew a hard line: PRE-LAUNCH vs.
    POST-LAUNCH failure are NOT the same thing and must never share a
    status.
      - PRE-LAUNCH (nothing could have run): no CLI entry wired for
        `tool_name`, an unmapped-but-overridden argument (F3, below), or
        the child process never actually started (e.g. the interpreter
        itself could not be exec'd). ``refused_stale_toolkit`` is still an
        ACCURATE description — refuse, as before.
      - POST-LAUNCH (the child started — it may have begun or finished a
        real write): a timeout, or output that fails to parse as JSON.
        Returns ``status='fresh_subprocess_outcome_unknown'`` instead —
        never a refusal, since "refused" implies nothing happened and we
        no longer know that.
      - STALE-ON-STALE: the child ran to completion and its OWN
        ``refuse_gate`` ALSO saw a stale module graph and refused before
        writing — this IS a fully known, verified outcome (refused,
        nothing touched). Returns the CHILD's own result verbatim (flagged
        ``nested_toolkit_stale``), never a second, fabricated refusal.

    F3 (compliance review, 2026-09-24): ``_tool_cli_argv`` only knows the
    tool's MCP-exposed params. A caller (almost always a test, or an
    internal composing tool) that also passes a NON-DEFAULT value for a
    param OUTSIDE that mapped set — `remote=`, `main_branch=`, `executor=`,
    `git_runner=`, `consent_rows=`, ... — would have that value SILENTLY
    DROPPED on the subprocess hop, running the child against a different
    target than the caller asked for. Checked BEFORE any subprocess is
    launched (still pre-launch, still a safe/accurate refusal).
    ``subprocess_run`` is a DI seam for tests (default: real
    ``subprocess.run``)."""
    argv = _tool_cli_argv(tool_name, kwargs)
    if argv is None:
        payload = refusal_payload(tool_name, verdict, allow_stale_toolkit)
        payload["error"] += (
            f" No fresh-subprocess CLI entry is wired for {tool_name!r} in "
            "toolkit_freshness._tool_cli_argv — refusing rather than "
            "guessing at a CLI shape. Nothing was launched; untouched."
        )
        return payload

    # F3: only meaningful for a tool that IS wired (`_MAPPED_PARAMS` above
    # is the assumed-safe subset for THAT tool's argv) — checked after the
    # "no CLI entry" branch so an entirely-unwired tool_name reports THAT
    # reason, not a misleading "every param is unmapped".
    unmapped_diffs = _unmapped_param_diffs(tool_name, fn_sig, kwargs)
    if unmapped_diffs:
        payload = refusal_payload(tool_name, verdict, allow_stale_toolkit)
        payload["error"] += (
            f" Cannot fresh-subprocess {tool_name!r}: caller passed a "
            f"non-default value for {unmapped_diffs} — none of these have "
            "a CLI flag (see toolkit_freshness._MAPPED_PARAMS), so silently "
            "dropping them on the subprocess hop would run the child "
            "against a DIFFERENT target than requested. Nothing was "
            "launched; untouched."
        )
        payload["unmapped_param_diffs"] = unmapped_diffs
        return payload

    cli_path = TOOLKIT_ROOT / "cli.py"
    # Explicit child env (F2): never inherit a stray PYTHONPATH the caller's
    # own process picked up (e.g. a worktree's product PYTHONPATH override
    # from an enclosing test/dispatch harness) — the fresh subprocess must
    # resolve `mcp/noctusai/**` and its deps the SAME way a bare `python
    # mcp/noctusai/cli.py` invocation would from a clean shell.
    child_env = {
        k: v for k, v in os.environ.items() if k != "PYTHONPATH"
    }
    runner = subprocess_run or (
        lambda cmd: (
            lambda p: (p.returncode, p.stdout, p.stderr)
        )(subprocess.run(cmd, capture_output=True, text=True, cwd=str(TOOLKIT_ROOT),
                         env=child_env, timeout=_FRESH_SUBPROCESS_TIMEOUT_S,
                         encoding="utf-8", errors="replace"))
    )
    cmd = [sys.executable, str(cli_path), *argv]
    try:
        rc, out, err = runner(cmd)
    except subprocess.TimeoutExpired as exc:
        # POST-LAUNCH: the child DID start (and subprocess.run's timeout
        # path kills it) — it may have been mid-write. Never a refusal.
        return _outcome_unknown_payload(
            tool_name, cmd, rc=None,
            out=exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace"),
            err=exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode("utf-8", "replace"),
            reason=f"timed out after {_FRESH_SUBPROCESS_TIMEOUT_S:.0f}s",
        )
    except OSError as exc:
        # PRE-LAUNCH ONLY (N1, compliance review, 2026-09-24): `OSError` —
        # `FileNotFoundError` (no such interpreter/cli.py),
        # `PermissionError`, `NotADirectoryError`, etc. — is the ONLY
        # exception family `subprocess.run`/`Popen` can raise BEFORE the
        # child process actually starts (the `os.execve`/`posix_spawn`
        # syscall itself failing). Every other exception a runner can raise
        # — `UnicodeDecodeError` from a bad `errors=`/`encoding=` on
        # captured output, a `ValueError` from a malformed `cmd`, an
        # injected test double's own bug — can ALSO occur after the child
        # has already run (e.g. decoding its stdout once it exited), so it
        # is UNSAFE to assume "nothing was launched" for those. Only THIS
        # branch is a genuine, accurate pre-launch refusal.
        payload = refusal_payload(tool_name, verdict, allow_stale_toolkit)
        payload["error"] += (
            f" Fresh-subprocess launch failed before the child could start "
            f"({' '.join(argv)}): {exc}. Nothing was launched; untouched."
        )
        return payload
    except Exception as exc:  # noqa: BLE001 — see N1 docstring note above
        # POST-LAUNCH (N1): anything OTHER than `OSError`/`TimeoutExpired`
        # raised by the runner (e.g. `UnicodeDecodeError` decoding the
        # child's captured output) does NOT prove the child never started —
        # it may have run to completion (or partway) before the failure.
        # Never a refusal; route through the same unknown-outcome contract
        # as an unparseable-output result, so the caller gets a
        # verification_step instead of a falsely reassuring "untouched".
        return _outcome_unknown_payload(
            tool_name, cmd, rc=None, out="", err=str(exc),
            reason=f"runner raised {type(exc).__name__} after launch: {exc}",
        )

    result = _extract_trailing_json(out) if out else None
    if not isinstance(result, dict):
        # POST-LAUNCH: the child ran (we have an rc) but produced no
        # parseable JSON — it may have crashed mid-write. Never a refusal.
        return _outcome_unknown_payload(
            tool_name, cmd, rc=rc, out=out, err=err, reason="unparseable output",
        )

    if result.get("toolkit_stale") is True:
        # The CHILD's own refuse_gate also saw stale and refused BEFORE
        # writing — a fully known, verified outcome. Return exactly what it
        # reported; never fabricate a second refusal on top of it.
        result["executed_via"] = "fresh_subprocess"
        result["nested_toolkit_stale"] = True
        # The PRIMARY process's own verdict (why we subprocessed at all) —
        # distinct from the CHILD's own `toolkit_stale`/`nested_toolkit_
        # stale` above, both carried so a caller can tell WHICH process was
        # stale without guessing from prose.
        result["primary_toolkit_stale"] = True
        result["primary_toolkit_freshness"] = verdict
        result.setdefault("warnings", [])
        # N2 (compliance review, 2026-09-24): "refused before writing" is
        # only an accurate claim when the child's OWN status is literally
        # `refused_stale_toolkit` (the pre-launch refuse_gate branch) —
        # `toolkit_stale=True` alone does not guarantee that; a future
        # child code path could set the flag on a POST-launch
        # outcome-unknown result too. Say the specific, verified thing when
        # we can; say the honest generic thing when we can't.
        if result.get("status") == "refused_stale_toolkit":
            result["warnings"].append(
                f"{tool_name}: the fresh subprocess ALSO reported its own "
                "module graph as stale and refused before writing — this "
                "is the CHILD's own (verified, nothing-touched) refusal, "
                "returned as-is, not a fabricated wrapper-level one."
            )
        else:
            result["warnings"].append(
                f"{tool_name}: the fresh subprocess ALSO reported its own "
                "module graph as stale (status="
                f"{result.get('status')!r}) — returned as-is, not a "
                "fabricated wrapper-level refusal. Whether anything was "
                "written depends on the CHILD's own status, not on this "
                "flag alone."
            )
        return result

    result["executed_via"] = "fresh_subprocess"
    result["primary_toolkit_stale"] = True
    result["primary_toolkit_freshness"] = verdict
    result.setdefault("warnings", [])
    result["warnings"].append(
        f"{tool_name}: the primary MCP server's module graph was stale, so "
        "this confirm=True write ran in a FRESH subprocess "
        "(`python mcp/noctusai/cli.py`) against the current on-disk code "
        "instead of refusing outright. The primary server should still be "
        f"restarted ({REMEDY}) — this fallback avoids blocking the caller "
        "on that, it does not replace it."
    )
    return result


def refuse_gate(
    tool_name: str,
    confirm_kwarg: str | None = "confirm",
    ttl_seconds: float = _DEFAULT_TTL_SECONDS,
    write_predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> Callable:
    """Decorator for the REFUSE posture: ``migrate_product``, ``release``,
    ``deploy_image``, and ``task_branch``'s mutating actions.

    Refuse-vs-warn line: **can a stale version silently produce a
    plausible-looking wrong result?** — not "does it touch prod." (The
    2026-09-18 incident's worked example: a stale ``task_branch action=
    start`` returned ``status: "started"``, exit 0, and a worktree that
    LOOKED fine, while silently omitting the `.env`/`node_modules`
    provisioning — a full day of engineer dispatches ran against
    unprovisioned trees before anyone noticed. `task_branch` never
    touches production; it still belongs in this posture because its
    stale answer was indistinguishable from a correct one.)

    ``migrate_product`` / ``release`` / ``deploy_image`` already gate their
    actual WRITE behind ``confirm=True`` (dry-run by default, same
    convention as ``allow_stale_tree`` / ``allow_inactive``) — the default
    ``confirm_kwarg="confirm"`` heuristic covers all three. A ``confirm=
    False`` call is a preview — it never touches anything, so it is safe
    to still answer with a loud warning (the WARN behaviour) rather than
    refuse outright, which would make the tool useless for "let me just
    check the plan" while stale.

    ``task_branch`` needs a richer predicate than "confirm alone" — only
    its MUTATING actions (``start`` / ``integrate`` / ``cleanup``) with
    ``confirm=True`` are a write; ``action='status'`` is always a read
    regardless of ``confirm``. Pass ``write_predicate`` (given the bound
    arguments dict, defaults applied) to override the confirm-kwarg
    heuristic entirely for that shape.

    Either way, a stale write no longer hard-refuses by default (R4,
    2026-09-24) — see the module docstring's "R4 — the fresh-subprocess
    fallback" section. It re-runs FRESH in a brand-new
    ``python mcp/noctusai/cli.py`` subprocess (``_run_via_fresh_subprocess``)
    and returns THAT result (``executed_via: "fresh_subprocess"``), falling
    back to the original hard refusal only when the subprocess path is
    itself impossible. ``allow_stale_toolkit=True`` still bypasses the
    refusal/subprocess decision entirely and runs IN-PROCESS (an escape
    hatch that is recorded on the return, never silent, mirroring
    ``allow_stale_tree``) — it is a DIFFERENT trust level than the
    subprocess fallback, not a superset of it.

    Adds keyword-only ``allow_stale_toolkit: bool = False`` and
    ``subprocess_run: Callable | None = None`` (a test-only DI seam for the
    R4 fallback's launcher — never MCP-exposed, same convention as
    ``run=``/``git_runner=``/``executor=``) to every decorated function
    WITHOUT changing its underlying signature (both popped out before the
    real call) — the MCP-facing ``register()`` wrapper in each decorated
    module declares ``allow_stale_toolkit`` explicitly so it is a real,
    documented tool argument.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            sig = None

        @functools.wraps(fn)
        def wrapper(*args: Any, allow_stale_toolkit: bool = False,
                   subprocess_run: Callable[..., tuple[int, str, str]] | None = None,
                   **kwargs: Any) -> Any:
            # Best-effort FULL bound-arguments dict (defaults applied) —
            # needed both for `write_predicate` AND (R4) as the kwargs the
            # fresh-subprocess fallback serializes to CLI flags. Falls back
            # to the raw kwargs on a bind failure (e.g. a positional-only
            # caller shape this signature can't introspect) — `is_write`
            # then degrades to "unknown ⇒ not a write" for `write_predicate`
            # callers (same behaviour as before this refactor), and the
            # fresh-subprocess mapping below just sees fewer kwargs.
            bound_args: dict[str, Any] = dict(kwargs)
            if sig is not None:
                try:
                    bound = sig.bind_partial(*args, **kwargs)
                    bound.apply_defaults()
                    bound_args = dict(bound.arguments)
                except TypeError:
                    pass

            is_write = False
            if write_predicate is not None:
                is_write = bool(write_predicate(bound_args))
            elif confirm_kwarg is not None:
                is_write = bool(bound_args.get(confirm_kwarg, kwargs.get(confirm_kwarg, False)))

            if is_write:
                verdict = check(ttl_seconds=ttl_seconds)
                if verdict["status"] == "stale" and not allow_stale_toolkit:
                    # R4 (2026-09-24): a stale-but-confirm=True write no
                    # longer hard-refuses by default — it re-runs FRESH, in
                    # a brand-new subprocess, against the current on-disk
                    # code. `allow_stale_toolkit=True` still means "I've
                    # manually verified this IN-PROCESS behaviour is safe" —
                    # it takes the OLD in-process path (below), never the
                    # subprocess one; the two escape hatches serve different
                    # trust levels and must not be conflated.
                    return _run_via_fresh_subprocess(
                        tool_name, bound_args, verdict, allow_stale_toolkit,
                        subprocess_run=subprocess_run, fn_sig=sig,
                    )
                result = fn(*args, **kwargs)
                if isinstance(result, dict):
                    result["toolkit_stale"] = verdict["status"] == "stale"
                    if result["toolkit_stale"]:
                        result.setdefault("warnings", [])
                        result["warnings"].append(stale_warning_message(verdict))
                        result["toolkit_freshness"] = verdict
                        result["allow_stale_toolkit"] = allow_stale_toolkit
                return result

            # Dry-run / read-only path: never refuse a preview — warn instead.
            result = fn(*args, **kwargs)
            if isinstance(result, dict):
                warn_if_stale(result, ttl_seconds=ttl_seconds)
            return result

        return wrapper

    return decorator


def register(server) -> None:
    @server.tool(
        name="noctus.dev.toolkit_freshness",
        description=(
            "Detects a STALE MCP server process — the class of bug behind the "
            "2026-09-18 incident, where ~30 hours of two-day-old task_branch.py "
            "code silently answered every noctus.dev.* call because Python "
            "caches an imported module and never re-reads its file. Returns "
            "{status: fresh|stale, changed_files, deleted_files, loaded_at, "
            "remedy}. A stale verdict never means 'this tool is broken' — it "
            "means 'restart the MCP server (`/mcp` in Claude Code) so it "
            "re-imports mcp/noctusai/** from disk.' The high-stakes tools "
            "(predeploy_check, deploy_verify, spa_smoke, migrate_product, "
            "release, deploy_image, task_branch) carry this verdict on their "
            "own return automatically (toolkit_stale + a warnings entry). "
            "Refuse-vs-warn is drawn on 'can a stale version silently "
            "produce a plausible-looking wrong result', not 'does it touch "
            "prod': migrate_product/release/deploy_image's confirm=True "
            "write, and task_branch's confirm=True start/integrate/cleanup "
            "(the incident tool itself — a stale start once returned "
            "status='started' exit 0 while silently skipping provisioning), "
            "all take the R4 fresh-subprocess fallback (2026-09-24) when "
            "stale — re-running the SAME call as `python mcp/noctusai/"
            "cli.py --<tool-flag> ...` in a brand-new process instead of "
            "hard-refusing, result carries executed_via='fresh_subprocess' "
            "— and only fall through to the original hard REFUSE (status="
            "'refused_stale_toolkit') when that fallback is itself "
            "impossible (no CLI entry wired, launch failure, unparseable "
            "output). action='status' and every confirm=False preview stay "
            "warn-only, never subprocessed. This tool always does a fresh "
            "stat pass (never the "
            "TTL-cached answer other tools use internally for cheapness) — "
            "calling it IS asking 'right now'. KB § PATTERNS/common/"
            "methodology-execution-discipline.md § 7."
        ),
    )
    def _toolkit_freshness() -> dict:
        verdict = check(bypass_cache=True)
        return {
            "ok": True,
            "status": verdict["status"],
            "changed_files": verdict["changed_files"],
            "deleted_files": verdict["deleted_files"],
            "loaded_at": verdict["loaded_at"],
            "checked_files": verdict["checked_files"],
            "check_duration_ms": verdict["check_duration_ms"],
            "remedy": verdict["remedy"],
        }


__all__ = [
    "TOOLKIT_ROOT",
    "REMEDY",
    "capture_baseline",
    "check",
    "stale_warning_message",
    "refusal_payload",
    "warn_if_stale",
    "warn_gate",
    "refuse_gate",
    "register",
]
