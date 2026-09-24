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
        ``None``), a subprocess launch failure, or unparseable subprocess
        output all fall back to the ORIGINAL hard refusal — never a silent
        working-tree call on unverified code.
      - ``_extract_trailing_json`` exists because ``cli.py`` can emit INFO
        log lines on stdout BEFORE its final ``json.dumps(...)`` — a naive
        whole-blob parse breaks on "Extra data" (found wiring this very
        fallback). NOC-REMEDIATE[cli-stdout-log-noise]: the cleaner
        platform fix is routing cli.py's logging to stderr, which would
        obsolete this extraction entirely — out of scope here — 2026-09-24.
"""
from __future__ import annotations

import functools
import inspect
import json
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
_FRESH_SUBPROCESS_TIMEOUT_S = 600.0

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
def _tool_cli_argv(tool_name: str, kwargs: dict[str, Any]) -> list[str] | None:
    """CLI argv (everything after ``cli.py``) for a gated write tool's bound
    kwargs. Returns ``None`` when `tool_name` has no wired entry."""
    if tool_name == "release":
        argv = ["--release", str(kwargs.get("stage") or "status")]
        if kwargs.get("confirm"):
            argv.append("--release-confirm")
        if kwargs.get("sha"):
            argv += ["--release-sha", str(kwargs["sha"])]
        mode = kwargs.get("mode") or "ff"
        if mode != "ff":
            argv += ["--release-mode", str(mode)]
        if kwargs.get("release_branch"):
            argv += ["--release-branch", str(kwargs["release_branch"])]
        return argv

    if tool_name == "migrate_product":
        product = kwargs.get("product")
        if not product:
            return None
        argv = ["--migrate-product", str(product)]
        if kwargs.get("confirm"):
            argv.append("--migrate-product-confirm")
        if kwargs.get("target"):
            argv += ["--migrate-product-target", str(kwargs["target"])]
        if kwargs.get("sha"):
            argv += ["--migrate-product-sha", str(kwargs["sha"])]
        if kwargs.get("project_ref"):
            argv += ["--migrate-product-project-ref", str(kwargs["project_ref"])]
        if kwargs.get("schema"):
            argv += ["--migrate-product-schema", str(kwargs["schema"])]
        if kwargs.get("worktree_path"):
            argv += ["--migrate-product-worktree-path", str(kwargs["worktree_path"])]
        if kwargs.get("allow_stale_tree"):
            argv.append("--migrate-product-allow-stale-tree")
        if kwargs.get("allow_inactive"):
            argv.append("--migrate-product-allow-inactive")
        return argv

    if tool_name == "deploy_image":
        product = kwargs.get("product")
        if not product:
            return None
        argv = ["--deploy-image", str(product)]
        if kwargs.get("confirm"):
            argv.append("--deploy-image-confirm")
        tag = kwargs.get("tag") or "latest"
        if tag != "latest":
            argv += ["--deploy-image-tag", str(tag)]
        source = kwargs.get("source") or "pull"
        if source != "pull":
            argv += ["--deploy-image-source", str(source)]
        ssh_host = kwargs.get("ssh_host") or "noctus-vps"
        if ssh_host != "noctus-vps":
            argv += ["--deploy-host", str(ssh_host)]
        if kwargs.get("skip_ancestry_check"):
            argv.append("--deploy-image-skip-ancestry-check")
        if kwargs.get("allow_inactive"):
            argv.append("--deploy-image-allow-inactive")
        return argv

    if tool_name == "task_branch":
        argv = ["--task-branch", str(kwargs.get("action") or "status")]
        if kwargs.get("slug"):
            argv += ["--task-branch-slug", str(kwargs["slug"])]
        if kwargs.get("confirm"):
            argv.append("--task-branch-confirm")
        if kwargs.get("project"):
            argv += ["--task-branch-project", str(kwargs["project"])]
        if kwargs.get("brief"):
            argv += ["--task-branch-brief", str(kwargs["brief"])]
        if kwargs.get("paths"):
            argv += ["--task-branch-paths", ",".join(str(p) for p in kwargs["paths"])]
        if kwargs.get("agent"):
            argv += ["--task-branch-agent", str(kwargs["agent"])]
        if kwargs.get("role"):
            argv += ["--task-branch-role", str(kwargs["role"])]
        if kwargs.get("parent"):
            argv += ["--task-branch-parent", str(kwargs["parent"])]
        if kwargs.get("wire_env") is False:
            argv.append("--task-branch-no-wire-env")
        if kwargs.get("verbose"):
            argv.append("--task-branch-verbose")
        return argv

    return None


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


def _run_via_fresh_subprocess(
    tool_name: str,
    kwargs: dict[str, Any],
    verdict: dict[str, Any],
    allow_stale_toolkit: bool,
    subprocess_run: Callable[..., tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """The R4 fallback: instead of refusing a confirm=True write outright
    because THIS process's module graph is stale, run the SAME call as
    ``python mcp/noctusai/cli.py --<tool-flag> ...`` in a brand-new
    subprocess — which re-imports ``mcp/noctusai/**`` from disk, so it can
    never itself be the stale process. Returns the subprocess's own JSON
    result with ``executed_via: "fresh_subprocess"`` added; ``toolkit_stale``
    rides through UNCHANGED from whatever the subprocess itself reports
    (almost always ``False`` — a process that just launched has nothing to
    have drifted from). Falls back to a hard refusal (never a silent
    working-tree call) when: no CLI entry is wired for `tool_name`; the
    subprocess itself fails to launch; its output isn't parseable JSON; or
    (defensive, expected-unreachable) the subprocess's OWN freshness check
    also comes back stale — each names the concrete reason in ``error``,
    never just "refused".
    ``subprocess_run`` is a DI seam for tests (default: real
    ``subprocess.run``)."""
    argv = _tool_cli_argv(tool_name, kwargs)
    if argv is None:
        payload = refusal_payload(tool_name, verdict, allow_stale_toolkit)
        payload["error"] += (
            f" No fresh-subprocess CLI entry is wired for {tool_name!r} in "
            "toolkit_freshness._tool_cli_argv — refusing rather than "
            "guessing at a CLI shape."
        )
        return payload

    cli_path = TOOLKIT_ROOT / "cli.py"
    runner = subprocess_run or (
        lambda cmd: (
            lambda p: (p.returncode, p.stdout, p.stderr)
        )(subprocess.run(cmd, capture_output=True, text=True, cwd=str(TOOLKIT_ROOT),
                         timeout=_FRESH_SUBPROCESS_TIMEOUT_S))
    )
    cmd = [sys.executable, str(cli_path), *argv]
    try:
        rc, out, err = runner(cmd)
    except Exception as exc:  # noqa: BLE001 — any launch failure is a hard refusal, named
        payload = refusal_payload(tool_name, verdict, allow_stale_toolkit)
        payload["error"] += f" Fresh-subprocess launch failed ({' '.join(argv)}): {exc}"
        return payload

    result = _extract_trailing_json(out) if out else None
    if not isinstance(result, dict):
        payload = refusal_payload(tool_name, verdict, allow_stale_toolkit)
        payload["error"] += (
            f" Fresh-subprocess produced unparseable output (rc={rc}): "
            f"{(err or out or '')[:500]}"
        )
        return payload

    if result.get("toolkit_stale") is True:
        # Defensive, expected-unreachable in practice: a process that just
        # launched has captured its OWN baseline moments ago, so it should
        # never itself report stale. If it somehow does (e.g. something
        # kept editing this toolkit's files WHILE the subprocess launched),
        # trust that verdict over "fresh_subprocess" optimism and hard-
        # refuse — never hand back a result that is stale-on-stale.
        payload = refusal_payload(tool_name, verdict, allow_stale_toolkit)
        payload["error"] += (
            " The fresh subprocess ALSO reported its own module graph as "
            "stale (toolkit_stale=True in its result) — refusing rather "
            "than trusting a stale-on-stale answer."
        )
        payload["fresh_subprocess_result"] = result
        return payload

    result["executed_via"] = "fresh_subprocess"
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
                        subprocess_run=subprocess_run,
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
