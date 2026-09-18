"""noctus.dev.gate_sweep — the canonical gate set for a change, MEASURED not
remembered; every gate its own subprocess, its own returncode.

WHY THIS TOOL EXISTS (two real incidents, 2026-09-17, same session)
---------------------------------------------------------------------
1. **Claimed green on a gate that was never run.** The tech-lead ran the seed
   suite + both product suites on a merged tip and reported "every gate green
   on the merged tip." `mcp/noctusai/tests/` was never run. CI then failed on
   exactly that suite (3 compliance failures). The claim was not a lie about
   a RESULT — it was a claim about a SET, made without checking the set was
   COMPLETE.
2. **Read an exit code that belonged to something else, twice** — see
   `KB § PATTERNS/common/methodology-execution-discipline.md` § 6
   "Verdict-channel integrity." `if git merge ... | tail -1; then` read
   tail's status, not merge's. `npx tsc --noEmit | tail -5 && echo
   "tsc-rc=$?"` printed as a gate result, and `$?` there is `tail`'s.

This tool makes both classes structurally hard, not just documented:

  - The gate SET is DERIVED from what actually changed (a git diff against
    `base_ref`, default `origin/dev`), never "whatever the agent remembered
    to run." A changed file with no known gate mapping is surfaced as its
    own `unmapped_diff` entry (`ran=False`) — never silently dropped from
    the count.
  - Every gate is run as its OWN `subprocess.run(...)` and its OWN
    `.returncode` is read directly — no pipe, no `tail`, no wrapper exit
    code standing in for the thing being judged.
  - `status="green"` is returned ONLY when every gate in `gates` has
    `ran=True AND exit_code==0`. Any gate that did not run (skipped,
    timed out, executable missing) makes the verdict `status="incomplete"`
    — **"not run" is a different color from "passed", always.** A gate
    that ran and failed makes it `status="red"`.

SCOPE DERIVATION
----------------
A changed path buckets into exactly one of:
  `products/<slug>/(backend|frontend)/...` -> that product's own gates
      (`pytest:<slug>` if `backend/tests/` exists, `vite_build:<slug>` if
      `frontend/package.json` exists).
  `seed/...`                                -> seed suites (the 4 seed pytest
      + vitest roots CI actually runs — `seed/{lib,framework}/{backend,
      frontend}`) PLUS fleet-wide (every product's own gates — everyone
      consumes `seed/`).
  `mcp/...`                                 -> `mcp_toolkit_tests`
      (`pytest mcp/noctusai/tests/ -q`, the very suite incident #1 skipped).
  KB/CLAUDE-doc paths, and ONLY those       -> `kb_sync_verify`
      (`cli.py --verify-kb-sync`), plus `claude_md_router`
      (`cli.py --check-claude-md-router`) when `CLAUDE.md` itself changed.
  anything else                             -> no known gate; surfaced as
      the `unmapped_diff` entry, which blocks `green` by construction.

STALE-TREE REFUSAL
-------------------
Mirrors `noctus.dev.migrate_product`'s stale-tree refusal EXACTLY (same
`GitRunner`/`FakeGitRunner`/`SubprocessGitRunner`/`_check_tree_staleness`,
imported — not reimplemented): if the resolved tree's current branch is
behind its own upstream tracking ref, a sweep run here cannot see what
actually landed there — the same "confident green that wasn't looking at
the real tree" shape as incident #1, one layer down. `status=
"refused_stale_tree"` unless `allow_stale_tree=True` (the bypass rides on
the result, never silent, same escape-hatch posture as `migrate_product`).

IO is injectable (`run_gate`, `git_runner`) — the colocated test drives
every branch (green / red / incomplete / stale-tree-refused / scope
derivation per bucket) with zero real subprocesses.
"""
from __future__ import annotations

import functools
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from settings import REPO_ROOT, resolve_test_python
from workspace import resolve_caller_root

from .build import _last_meaningful_line
from .migrate_product import (
    FakeGitRunner,  # noqa: F401  (re-exported for test convenience)
    GitQueryError,
    GitRunner,
    SubprocessGitRunner,
    _check_tree_staleness,
)

# ---------------------------------------------------------------------------
# Scope derivation — a changed path buckets into exactly one gate-family.
# ---------------------------------------------------------------------------

_PRODUCT_RE = re.compile(r"^products/([^/]+)/(?:backend|frontend)/")
_SEED_FLEET_RE = re.compile(r"^seed/")
_MCP_RE = re.compile(r"^mcp/")
_KB_DOC_RE = re.compile(
    r"^(KNOWLEDGE-BASE/|CLAUDE\.md$|CLAUDE/|\.claude/(agents|skills|commands)/)"
)

# The seed roots CI actually runs as their own jobs (Seed Backend/Frontend
# Tests) — NOT `products/seed`, which is the dogfood reference PRODUCT and
# is already covered by `_PRODUCT_RE` under slug "seed". These two names
# collide on purpose (both are "the seed"); the regexes never do, because
# `_PRODUCT_RE` requires the `products/` prefix and `_SEED_FLEET_RE` matches
# only the top-level `seed/` framework+lib tree.
_SEED_PYTEST_ROOTS = ("seed/lib/backend", "seed/framework/backend")
_SEED_VITEST_ROOTS = ("seed/lib/frontend", "seed/framework/frontend")


def _porcelain_paths(status_short: str) -> list[str]:
    """Repo-relative paths from `git status --porcelain` (`XY <path>`, or
    the rename shape `XY <old> -> <new>` where the new path is the one that
    matters). Mirrors the parser `noctus.dev.deploy_pull` /
    `noctus.dev.migrate_product` each carry their own narrow copy of —
    genuinely tiny (porcelain has no library-grade parser worth importing
    for 6 lines), not worth a cross-module import for.
    """
    out: list[str] = []
    for line in (status_short or "").splitlines():
        if len(line) <= 3:
            continue
        path_part = line[3:]
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1]
        out.append(path_part.strip().strip('"'))
    return out


def _changed_files(
    root: Path, git_runner: GitRunner, base_ref: str
) -> tuple[list[str], list[str]]:
    """Committed diff against `base_ref` (three-dot — "what did HEAD add
    since it diverged from base_ref") UNION uncommitted `git status`
    changes. Returns `(files, warnings)` — a query that fails (e.g.
    `base_ref` unresolvable) is surfaced as a warning, never silently
    swallowed into an empty-and-indistinguishable-from-clean diff."""
    files: set[str] = set()
    warnings: list[str] = []
    try:
        diff_out = git_runner.run(root, ["diff", "--name-only", f"{base_ref}...HEAD"])
        files.update(p.strip() for p in diff_out.splitlines() if p.strip())
    except GitQueryError as exc:
        warnings.append(
            f"could not diff against {base_ref!r} ({exc}); scope derivation is "
            "based on uncommitted changes only — this is a SMALLER set than "
            "the true diff, never a larger one"
        )
    try:
        status_out = git_runner.run(root, ["status", "--porcelain"])
        files.update(_porcelain_paths(status_out))
    except GitQueryError as exc:
        warnings.append(f"could not read `git status --porcelain` ({exc})")
    return sorted(files), warnings


def _derive_scope(files: list[str]) -> dict[str, Any]:
    """Bucket every changed path into exactly one gate-family. See module
    docstring "SCOPE DERIVATION"."""
    products: set[str] = set()
    seed_fleet_wide = False
    mcp_touched = False
    doc_files: list[str] = []
    other_files: list[str] = []
    for f in files:
        m = _PRODUCT_RE.match(f)
        if m:
            products.add(m.group(1))
            continue
        if _SEED_FLEET_RE.match(f):
            seed_fleet_wide = True
            continue
        if _MCP_RE.match(f):
            mcp_touched = True
            continue
        if _KB_DOC_RE.match(f):
            doc_files.append(f)
            continue
        other_files.append(f)
    doc_only = (
        bool(doc_files) and not products and not seed_fleet_wide
        and not mcp_touched and not other_files
    )
    return {
        "products": sorted(products),
        "seed_fleet_wide": seed_fleet_wide,
        "mcp": mcp_touched,
        "doc_only": doc_only,
        "doc_files": sorted(doc_files),
        "unmapped_files": sorted(other_files),
        "claude_md_touched": "CLAUDE.md" in files,
    }


# ---------------------------------------------------------------------------
# Gate catalog — every gate is (name, argv, cwd). `argv=None` means the gate
# is structurally not applicable (e.g. a product with no frontend) and is
# simply never listed — NOT the same thing as a listed-but-skipped gate
# (which blocks `green`; see `_run_gates`).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateSpec:
    gate: str
    argv: list[str]
    cwd: Path


def _all_product_slugs(root: Path) -> list[str]:
    products_dir = root / "products"
    if not products_dir.exists():
        return []
    return sorted(
        d.name for d in products_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )


def _product_gate_specs(root: Path, slug: str, py: str) -> list[GateSpec]:
    specs: list[GateSpec] = []
    backend = root / "products" / slug / "backend"
    if (backend / "tests").exists():
        specs.append(
            GateSpec(f"pytest:{slug}", [py, "-m", "pytest", "-q", "--tb=short"], backend)
        )
    frontend = root / "products" / slug / "frontend"
    if (frontend / "package.json").exists():
        specs.append(GateSpec(f"vite_build:{slug}", ["npx", "vite", "build"], frontend))
    return specs


def _seed_gate_specs(root: Path, py: str) -> list[GateSpec]:
    specs: list[GateSpec] = []
    for rel in _SEED_PYTEST_ROOTS:
        d = root / rel
        if (d / "tests").exists():
            specs.append(GateSpec(f"pytest:{rel}", [py, "-m", "pytest", "-q", "--tb=short"], d))
    for rel in _SEED_VITEST_ROOTS:
        d = root / rel
        if (d / "package.json").exists():
            specs.append(GateSpec(f"vitest:{rel}", ["npm", "test"], d))
    return specs


def _build_gate_specs(root: Path, scope: dict[str, Any]) -> list[GateSpec]:
    py = resolve_test_python()
    specs: list[GateSpec] = []

    if scope["seed_fleet_wide"]:
        specs.extend(_seed_gate_specs(root, py))
        for slug in _all_product_slugs(root):
            specs.extend(_product_gate_specs(root, slug, py))
    else:
        for slug in scope["products"]:
            specs.extend(_product_gate_specs(root, slug, py))

    if scope["mcp"]:
        specs.append(
            GateSpec("mcp_toolkit_tests", [py, "-m", "pytest", "mcp/noctusai/tests/", "-q"], root)
        )

    if scope["doc_only"]:
        specs.append(
            GateSpec("kb_sync_verify", [py, "mcp/noctusai/cli.py", "--verify-kb-sync"], root)
        )
        if scope["claude_md_touched"]:
            specs.append(
                GateSpec(
                    "claude_md_router",
                    [py, "mcp/noctusai/cli.py", "--check-claude-md-router"],
                    root,
                )
            )

    return specs


# ---------------------------------------------------------------------------
# The gate runner — ONE subprocess, ONE returncode, per gate. This is the
# whole point of the tool: no pipeline sits between a gate and its verdict.
# ---------------------------------------------------------------------------

GateRunResult = tuple  # (exit_code: int | None, summary: str, duration_s: float)


def _default_run_gate(spec: GateSpec, timeout: int = 300) -> GateRunResult:
    """Run ONE gate as its OWN subprocess; return its OWN `.returncode`
    directly. `exit_code=None` means the gate did not produce a verdict at
    all (timeout, missing executable) — never conflated with `0`."""
    start = time.time()
    try:
        proc = subprocess.run(
            spec.argv, cwd=str(spec.cwd), capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"timeout after {timeout}s", time.time() - start
    except OSError as exc:
        return None, f"could not run {spec.argv[0]!r}: {exc}", time.time() - start
    duration = time.time() - start
    combined = (proc.stdout or "") + (proc.stderr or "")
    summary = _last_meaningful_line(combined) if combined.strip() else "(no output)"
    return proc.returncode, summary, duration


def _run_gates(
    specs: list[GateSpec], run_gate: Callable[[GateSpec], GateRunResult]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for spec in specs:
        exit_code, summary, duration = run_gate(spec)
        results.append({
            "gate": spec.gate,
            "ran": exit_code is not None,
            "exit_code": exit_code,
            "summary": summary,
            "duration_s": round(duration, 2),
        })
    return results


def _verdict(gates: list[dict[str, Any]]) -> str:
    """`green` iff every gate ran AND exited 0. A real failure (`red`) is
    reported ahead of a mere non-run (`incomplete`) when both are present —
    a known failure is more actionable than an unknown. `green` is the
    empty-set default (nothing applicable, nothing to fail) — vacuous but
    never silently wrong, since `gates=[]` rides on the result too."""
    if any(g["ran"] and g["exit_code"] != 0 for g in gates):
        return "red"
    if any(not g["ran"] for g in gates):
        return "incomplete"
    return "green"


# ---------------------------------------------------------------------------


def gate_sweep(
    base_ref: str = "origin/dev",
    worktree_path: str | None = None,
    repo_root: str | None = None,
    allow_stale_tree: bool = False,
    timeout: int = 300,
    run_gate: Callable[[GateSpec], GateRunResult] | None = None,
    git_runner: GitRunner | None = None,
) -> dict[str, Any]:
    """Run the canonical gate set for what actually changed vs. `base_ref`;
    return a structured, measured verdict. See module docstring.

    Args:
        base_ref: the ref this branch's diff is measured against
            (default `origin/dev` — the integration branch every feature
            branch is meant to compare against).
        worktree_path: pin the tree (same semantics as `migrate_product` /
            `predeploy_check` — pass this from inside a git worktree so the
            sweep runs against THAT tree, not the MCP server's fixed-CWD
            primary).
        repo_root: explicit override for the tree (test seam — wins over
            `worktree_path`).
        allow_stale_tree: escape hatch for the stale-tree refusal (see
            module docstring). The bypass rides on the result's
            `stale_tree` key even when set — never silent.
        timeout: per-gate subprocess timeout in seconds.
        run_gate: injectable gate runner (test seam) — `(spec) ->
            (exit_code, summary, duration_s)`.
        git_runner: injectable `GitRunner` (test seam) — same Protocol
            `noctus.dev.migrate_product` uses.

    Returns:
        {ok, status ('green'|'red'|'incomplete'|'refused_stale_tree'|
         'error'), exit_code, base_ref, resolved_root, changed_files,
         scope, gates, stale_tree, allow_stale_tree, warnings, error?}
    """
    runner_git = git_runner or SubprocessGitRunner()
    if repo_root is not None:
        root = Path(repo_root)
    elif worktree_path:
        root = Path(resolve_caller_root(worktree_path))
    else:
        root = Path(REPO_ROOT)

    if not root.is_dir():
        return {
            "ok": False, "status": "error", "exit_code": 1,
            "error": f"resolved root does not exist: {root}",
        }

    stale_tree = _check_tree_staleness(root, git_runner=runner_git)
    if stale_tree["stale"] and not allow_stale_tree:
        return {
            "ok": True,
            "status": "refused_stale_tree",
            "exit_code": 1,
            "base_ref": base_ref,
            "resolved_root": str(root),
            "changed_files": [],
            "scope": None,
            "gates": [],
            "warnings": [],
            "stale_tree": stale_tree,
            "allow_stale_tree": allow_stale_tree,
            "error": (
                f"refusing to sweep a stale tree ({stale_tree['detail']}) — the "
                "sweep would be blind to whatever actually landed upstream. "
                "Fetch/rebase first (git merge --ff-only "
                f"{stale_tree.get('upstream') or '<upstream>'}), or pass "
                "allow_stale_tree=True to override deliberately (recorded, "
                "never silent, mirrors noctus.dev.migrate_product)."
            ),
        }

    changed_files, warnings = _changed_files(root, runner_git, base_ref)
    scope = _derive_scope(changed_files)
    specs = _build_gate_specs(root, scope)
    runner = run_gate or functools.partial(_default_run_gate, timeout=timeout)

    gates = _run_gates(specs, runner)

    if scope["unmapped_files"]:
        gates.append({
            "gate": "unmapped_diff",
            "ran": False,
            "exit_code": None,
            "summary": (
                f"{len(scope['unmapped_files'])} changed file(s) have no known "
                f"gate mapping: {scope['unmapped_files'][:20]}"
                + (" …" if len(scope["unmapped_files"]) > 20 else "")
            ),
            "duration_s": 0.0,
        })

    status = _verdict(gates)
    return {
        "ok": True,
        "status": status,
        "exit_code": 0 if status == "green" else 1,
        "base_ref": base_ref,
        "resolved_root": str(root),
        "changed_files": changed_files,
        "scope": scope,
        "gates": gates,
        "warnings": warnings,
        "stale_tree": stale_tree,
        "allow_stale_tree": allow_stale_tree,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.gate_sweep",
        description=(
            "Run the CANONICAL gate set for a change and return a structured, "
            "MEASURED verdict — never a remembered one. Derives WHICH gates "
            "apply from a git diff against base_ref (default 'origin/dev'): a "
            "products/<slug> diff -> that product's own pytest+vite_build "
            "gates; a seed/ diff -> the 4 seed pytest/vitest roots PLUS "
            "fleet-wide (every product); an mcp/ diff -> "
            "mcp/noctusai/tests/; a KB/CLAUDE-doc-ONLY diff -> "
            "--verify-kb-sync (+--check-claude-md-router if CLAUDE.md itself "
            "changed). A changed file with no known mapping becomes its own "
            "'unmapped_diff' entry (ran=False) rather than being silently "
            "dropped. Every gate runs as its OWN subprocess and its OWN "
            "returncode is read directly (KB § PATTERNS/common/"
            "methodology-execution-discipline.md § 6, verdict-channel "
            "integrity) — never a shell pipeline, never a parsed tail. "
            "status='green' ONLY when every gate has ran=True AND "
            "exit_code==0; a gate that never ran forces status='incomplete' "
            "(never green); a gate that ran and failed forces status='red'. "
            "Pass worktree_path when called from inside a git worktree — "
            "same semantics as noctus.dev.migrate_product/predeploy_check, "
            "including its stale-tree refusal posture (status="
            "'refused_stale_tree' when the tree is behind its own upstream — "
            "a stale tree must not yield a green sweep; allow_stale_tree=True "
            "is the recorded escape hatch)."
        ),
    )
    def _gate_sweep(
        base_ref: str = "origin/dev",
        worktree_path: str | None = None,
        allow_stale_tree: bool = False,
        timeout: int = 300,
    ) -> dict:
        return gate_sweep(
            base_ref=base_ref,
            worktree_path=worktree_path,
            allow_stale_tree=allow_stale_tree,
            timeout=timeout,
        )


__all__ = [
    "GateSpec",
    "gate_sweep",
    "register",
    "_derive_scope",
    "_changed_files",
    "_build_gate_specs",
    "_default_run_gate",
    "_verdict",
    "_porcelain_paths",
    "_all_product_slugs",
]
