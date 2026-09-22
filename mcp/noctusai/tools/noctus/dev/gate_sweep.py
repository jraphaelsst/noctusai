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
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from settings import REPO_ROOT, resolve_test_python
from workspace import resolve_caller_root

from .build import _last_meaningful_line
from .harness_signatures import HARNESS_SIGNATURES as _HARNESS_SIGNATURES
from .harness_signatures import harness_suspect as _harness_suspect
from .migrate_product import (
    FakeGitRunner,  # noqa: F401  (re-exported for test convenience)
    GitQueryError,
    GitRunner,
    SubprocessGitRunner,
    _check_tree_staleness,
)
from .product_scope import filter_active

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
        # Populated by `_build_gate_specs` — ASLEEP products dropped from a
        # `seed_fleet_wide` fan-out (never silently; see `product_scope.py`).
        "skipped_asleep": [],
    }


# ---------------------------------------------------------------------------
# Gate catalog — every gate is (name, argv, cwd). `argv=None` means the gate
# is structurally not applicable (e.g. a product with no frontend) and is
# simply never listed — NOT the same thing as a listed-but-skipped gate
# (which blocks `green`; see `_run_gates`).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# HARNESS VALIDITY — a verdict is evidence about the SUBJECT only if the
# harness that produced it was VALID.
#
# § 6 (verdict-channel integrity) says: read the exit code that belongs to
# the thing you are judging. This is the failure ONE STEP EARLIER, and it is
# NOT fixed by reading more carefully: the exit code genuinely belongs to the
# command you ran, the command genuinely failed — and the failure is about
# the HARNESS, not the subject. A missing browser binary, an unwired
# `node_modules`, a venv-less interpreter and a dev server that never booted
# all produce an authoritative, correctly-attributed, completely
# uninformative red.
#
# Measured, 2026-09-20, one Playwright investigation, SEVEN of them:
#   1. browser binary never installed        -> "test failed"
#   2. browser revision PRUNED by installing
#      a second @playwright/test version     -> "test failed"
#   3. tree 41 commits stale                 -> "baseline green"   (§ 7)
#   4. `tail -8` ate the summary line        -> "1 passed"         (§ 6)
#   5. worktree seed dirs had no node_modules
#      so vite never resolved the app        -> "11 tests failed"
#   6. no env_bootstrap                      -> "predeploy blocked"
#   7. `start.sh` missing from a staged tree
#      so the dev server never started       -> "reproduced on Linux"
# Not one of those verdicts described the code under test. Each looked exactly
# like one that did.
#
# TWO LEGS, because the class has two halves:
#   (a) PREFLIGHT  — a cheap, definitive path probe asserted BEFORE the gate
#       runs. Unmet => the gate is NOT RUN AT ALL, so there is no exit code to
#       misread; the fault is NAMED with a remedy instead of guessed at.
#   (b) SIGNATURE  — for what preflight cannot know in advance, match the
#       tool's OWN distinctive setup-failure output on a non-zero exit and
#       mark the gate `harness_suspect`. Advisory by construction: the
#       evidence line always rides along, so a wrong guess is visible and
#       overrulable rather than silently swallowing a real red. The
#       signature catalog itself (`_HARNESS_SIGNATURES` / `_harness_suspect`)
#       now lives in the sibling `harness_signatures.py` module — SHARED
#       with the `claude-guard-harness-signature` PostToolUse Bash hook, so
#       an ad-hoc Bash call outside this sweep gets the same classification
#       (2026-09-20: a wrong argparse invocation run directly in Bash, never
#       through `gate_sweep`, was reported as "6 failing products").
#
# The verdict rule that makes this load-bearing: a failing gate that carries
# a `harness_suspect` is NOT a trustworthy red. If EVERY failure is suspect,
# the sweep is `inconclusive`, never `red` — because "I could not measure"
# must never be reported as "it failed". That is the whole bug: a red you
# cannot trust is worse than no red, because you ACT on it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Precondition:
    """One cheap, named, DEFINITIVE assertion about the harness.

    `path` must exist for a run of this gate to say anything about the code.
    Checked before the gate runs; a miss names itself and its `remedy`."""

    name: str
    path: Path
    remedy: str


def _pkg_json(pkg_dir: Path) -> dict[str, Any]:
    """Read a package.json. An unreadable/malformed one yields `{}`, which
    means FEWER preconditions are derived — i.e. it degrades to the exact
    behaviour this module had before preconditions existed, never to a
    false green (an underived precondition cannot pass; it simply is not
    asserted, and the gate still runs and is still judged on its own exit
    code)."""
    try:
        return json.loads((pkg_dir / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _node_preconditions(pkg_dir: Path, *, playwright: bool = False) -> tuple[Precondition, ...]:
    """Preconditions for any npm-run gate in `pkg_dir`.

    `@noctusai/*` deps are `file:`-linked to the seed and are what an
    unwired worktree is missing — vite resolves them at BUILD time, so
    their absence surfaces as an app that renders nothing and a suite that
    'fails' on every assertion (measured 2026-09-20, 11 'failures')."""
    pres = [
        Precondition(
            name="node_modules",
            # 🔴 `.package-lock.json`, NOT the directory. `npm ci`/`npm install`
            # write that file; nothing else does. A bare `node_modules/` proves
            # only that SOMETHING made a directory — and something does:
            # `task_branch wire_env` links `node_modules/@noctusai/{lib,seed}`
            # into a product even when it SKIPPED the base `node_modules` link
            # (primary had none), leaving a directory holding two symlinks and
            # no packages. Measured 2026-09-20: that partial dir passed a
            # dir-exists precondition, so `vite_build:academia-de-reciclagem`
            # RAN and failed on `Cannot find module 'tailwindcss'` — a red about
            # the wiring, wearing the clothes of a red about the code. The
            # marker file is the only thing that distinguishes "installed here"
            # from "a directory exists here".
            path=pkg_dir / "node_modules" / ".package-lock.json",
            remedy=(
                f"npm ci --legacy-peer-deps in {pkg_dir} — node_modules/ may "
                "EXIST but hold only wire_env's @noctusai symlinks; the "
                "npm-written .package-lock.json marker is absent, so nothing "
                "is actually installed there"
            ),
        )
    ]
    deps = _pkg_json(pkg_dir).get("dependencies") or {}
    for dep in sorted(k for k in deps if k.startswith("@noctusai/")):
        pres.append(
            Precondition(
                name=dep,
                path=pkg_dir / "node_modules" / Path(dep),
                remedy=(
                    f"{dep} is a file:-linked seed dep that `npm ci` does NOT "
                    "install — wire it with task_branch wire_env=True"
                ),
            )
        )
    if playwright:
        pres.append(
            Precondition(
                name="@playwright/test",
                path=pkg_dir / "node_modules" / "@playwright" / "test",
                remedy="the e2e runner itself is absent — npm ci in the product frontend",
            )
        )
    return tuple(pres)


@dataclass(frozen=True)
class GateSpec:
    gate: str
    argv: list[str]
    cwd: Path
    preconditions: tuple[Precondition, ...] = ()


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
        specs.append(
            GateSpec(
                f"vite_build:{slug}", ["npx", "vite", "build"], frontend,
                _node_preconditions(frontend),
            )
        )
        # The e2e suite CI runs. It was absent from this sweep until
        # 2026-09-20 — which is precisely why a Playwright investigation ran
        # entirely in hand-rolled shell, outside every structural protection
        # this module provides, and collected seven harness-invalid verdicts.
        # A gate CI enforces but the local sweep omits is the "incomplete SET"
        # failure this tool was built for, one directory over.
        if (frontend / "playwright.config.ts").exists() and (frontend / "e2e").is_dir():
            specs.append(
                GateSpec(
                    f"e2e:{slug}", ["npx", "playwright", "test"], frontend,
                    _node_preconditions(frontend, playwright=True),
                )
            )
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
            specs.append(GateSpec(f"vitest:{rel}", ["npm", "test"], d, _node_preconditions(d)))
    return specs


def _build_gate_specs(root: Path, scope: dict[str, Any]) -> list[GateSpec]:
    py = resolve_test_python()
    specs: list[GateSpec] = []

    if scope["seed_fleet_wide"]:
        specs.extend(_seed_gate_specs(root, py))
        # A seed change fans out to every product's own gates — but only
        # the ACTIVE (awake) ones. An asleep product (dormant_slugs, per
        # deploy/fleet/active-scope.txt) is surfaced in `skipped_asleep`,
        # never dropped silently (see product_scope.py's module docstring).
        all_slugs = _all_product_slugs(root)
        active_slugs = filter_active(all_slugs, root=root)
        scope["skipped_asleep"] = sorted(set(all_slugs) - set(active_slugs))
        for slug in active_slugs:
            specs.extend(_product_gate_specs(root, slug, py))
    else:
        # Products here come from an ACTUAL diff under products/<slug>/ —
        # already an explicit signal (someone is touching that product's
        # code). Never filtered out, but an asleep one is flagged: the
        # user may be deliberately waking it.
        asleep_requested = sorted(
            set(scope["products"]) - set(filter_active(scope["products"], root=root))
        )
        if asleep_requested:
            scope["asleep_requested"] = asleep_requested
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

# (exit_code: int | None, summary: str, duration_s: float[, output: str])
# The 4th element is the FULL captured output, needed to match harness
# signatures. A 3-tuple runner stays valid (every pre-2026-09-20 test seam
# injects one): `_run_gates` then matches signatures against the summary
# line alone — degraded reach, never a wrong answer.
GateRunResult = tuple


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
    return proc.returncode, summary, duration, combined


def _run_gates(
    specs: list[GateSpec], run_gate: Callable[[GateSpec], GateRunResult]
) -> list[dict[str, Any]]:
    """Preflight, then run, then classify — in that order.

    A gate whose preconditions are unmet is NOT RUN. That is the point: an
    unrun gate has no exit code to be mistaken for a verdict about the
    code. It is recorded `ran=False` with `harness_invalid` naming what is
    missing and how to fix it."""
    results: list[dict[str, Any]] = []
    for spec in specs:
        unmet = [p for p in spec.preconditions if not p.path.exists()]
        if unmet:
            results.append({
                "gate": spec.gate,
                "ran": False,
                "exit_code": None,
                "summary": (
                    "HARNESS INVALID — gate NOT run (its result would have "
                    "described the setup, not the code): "
                    + ", ".join(p.name for p in unmet)
                ),
                "duration_s": 0.0,
                "harness_invalid": [
                    {"precondition": p.name, "missing_path": str(p.path), "remedy": p.remedy}
                    for p in unmet
                ],
            })
            continue

        raw = run_gate(spec)
        # 3-tuple seams stay supported; see GateRunResult.
        exit_code, summary, duration, output = raw if len(raw) == 4 else (*raw, raw[1])
        entry: dict[str, Any] = {
            "gate": spec.gate,
            "ran": exit_code is not None,
            "exit_code": exit_code,
            "summary": summary,
            "duration_s": round(duration, 2),
        }
        if exit_code not in (0, None):
            suspect = _harness_suspect(output or "", exit_code)
            if suspect:
                entry["harness_suspect"] = suspect
        results.append(entry)
    return results


def _verdict(gates: list[dict[str, Any]]) -> str:
    """`green` iff every gate ran AND exited 0.

    Precedence, and the reasoning for it:

    - `red` — at least one gate failed on a VALID harness. A known real
      failure is the most actionable thing there is, so it outranks
      everything below (unchanged: a known failure beats an unknown).
    - `inconclusive` — there are failures, but EVERY ONE of them carries a
      `harness_suspect`; or some gate never ran because a precondition was
      unmet. No trustworthy red exists, so calling this `red` would assert
      something about the code that was never measured. **This is the whole
      point of the state:** a red you cannot trust is worse than no red,
      because you act on it — a disproven-but-plausible mechanism gets
      written down, a version gets pinned, and the real bug stays hidden.
    - `incomplete` — a gate did not run for a reason that is NOT a named
      harness fault (timeout, unmapped diff).
    - `green` — every gate ran and passed. Also the empty-set default
      (vacuous, but `gates=[]` rides on the result, so never silently
      wrong)."""
    failed = [g for g in gates if g["ran"] and g["exit_code"] != 0]
    if any(not g.get("harness_suspect") for g in failed):
        return "red"
    if failed or any(g.get("harness_invalid") for g in gates):
        return "inconclusive"
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
        {ok, status ('green'|'red'|'inconclusive'|'incomplete'|
         'refused_stale_tree'|'error'), exit_code, harness, base_ref,
         resolved_root, changed_files, scope, gates, stale_tree,
         allow_stale_tree, warnings, error?}

        `harness` = {invalid: [...], suspects: [...]} — the gates whose
        PRECONDITIONS were unmet (never run), and the failing gates whose
        output carried a known harness-failure signature. Both are the
        answer to "is this red about my code?", which is the question a
        red does not answer by itself. `status='inconclusive'` means: no
        trustworthy red exists — fix the harness, then measure again.
        Its `exit_code` is 1, never 0: not-measured is not a pass.
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
    harness = {
        "invalid": [
            {"gate": g["gate"], **item}
            for g in gates
            for item in g.get("harness_invalid", [])
        ],
        "suspects": [
            {"gate": g["gate"], **g["harness_suspect"]}
            for g in gates
            if g.get("harness_suspect")
        ],
    }
    return {
        "ok": True,
        "status": status,
        "exit_code": 0 if status == "green" else 1,
        "harness": harness,
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
            "HARNESS VALIDITY (2026-09-20): a gate whose preconditions are "
            "unmet (no node_modules, an unlinked file:-linked @noctusai/* "
            "seed dep, no @playwright/test) is NOT RUN — it is reported "
            "harness_invalid with a remedy, because running it would yield "
            "a red that describes the SETUP, not the code. A gate that "
            "fails with a known setup signature in its output (missing "
            "Playwright browser, dev server never started, bare specifier "
            "unresolved, venv-less worktree) is marked harness_suspect and "
            "carries the matched evidence line. When EVERY failure is "
            "suspect, status='inconclusive' (exit 1) rather than 'red' — "
            "an unmeasurable gate must never be reported as a measured "
            "failure. Products with playwright.config.ts + e2e/ now "
            "contribute an e2e:<slug> gate, so the local sweep covers the "
            "suite CI actually enforces. "
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
    "Precondition",
    "_harness_suspect",
    "_node_preconditions",
    "_HARNESS_SIGNATURES",
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
