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
    Hot-reload. Swapping code under a live module graph mid-call is a much
    worse failure mode than reporting staleness — the remedy is always
    "restart the MCP server" (``/mcp`` in Claude Code), never a live patch.
"""
from __future__ import annotations

import functools
import inspect
import sys
import time
from pathlib import Path
from typing import Any, Callable

# .../mcp/noctusai/tools/noctus/dev/toolkit_freshness.py -> parents[3] == mcp/noctusai
TOOLKIT_ROOT: Path = Path(__file__).resolve().parents[3]

REMEDY = "Restart the MCP server (Claude Code: run `/mcp`) so it re-imports mcp/noctusai/** from disk."

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

    Either way, a refused write is refused unless the caller explicitly
    passes ``allow_stale_toolkit=True`` (an escape hatch that is recorded
    on the return, never silent, mirroring ``allow_stale_tree``).

    Adds a keyword-only ``allow_stale_toolkit: bool = False`` to every
    decorated function WITHOUT changing its underlying signature (popped
    out of ``kwargs`` before the real call) — the MCP-facing
    ``register()`` wrapper in each decorated module declares the param
    explicitly so it is a real, documented tool argument.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            sig = None

        @functools.wraps(fn)
        def wrapper(*args: Any, allow_stale_toolkit: bool = False, **kwargs: Any) -> Any:
            is_write = False
            if write_predicate is not None:
                bound_args: dict[str, Any] = dict(kwargs)
                if sig is not None:
                    try:
                        bound = sig.bind_partial(*args, **kwargs)
                        bound.apply_defaults()
                        bound_args = dict(bound.arguments)
                    except TypeError:
                        pass
                is_write = bool(write_predicate(bound_args))
            elif confirm_kwarg is not None:
                if confirm_kwarg in kwargs:
                    is_write = bool(kwargs[confirm_kwarg])
                elif sig is not None:
                    try:
                        bound = sig.bind_partial(*args, **kwargs)
                        is_write = bool(bound.arguments.get(confirm_kwarg, False))
                    except TypeError:
                        is_write = False

            if is_write:
                verdict = check(ttl_seconds=ttl_seconds)
                if verdict["status"] == "stale" and not allow_stale_toolkit:
                    return refusal_payload(tool_name, verdict, allow_stale_toolkit)
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
            "prod': migrate_product/release/deploy_image REFUSE their "
            "confirm=True write, and task_branch REFUSES its confirm=True "
            "start/integrate/cleanup (the incident tool itself — a stale "
            "start once returned status='started' exit 0 while silently "
            "skipping provisioning); action='status' and every confirm="
            "False preview stay warn-only. This tool always does a fresh "
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
