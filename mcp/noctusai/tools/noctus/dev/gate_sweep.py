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
  `seed/...`                                -> seed suites PLUS the products the
      change can reach (2026-10-09 — was: every active product x pytest +
      vite_build + e2e, which blew the merged-tip time-box on every seed
      integrate). `_seed_fanout_plan` classifies each seed file: `.md`
      ignored; `*/backend/tests/**` / FE test files -> that seed suite only;
      `.py` under `noctusai_lib` / `noctusai_seed` -> changed python module,
      expanded by REVERSE TRANSITIVE CLOSURE over the seed import graph
      (absolute + relative imports; importing `a.b.c` also depends on `a`,
      `a.b`), and a product is a py-consumer iff any .py under its backend
      (app + tests) imports an affected module; non-test files under
      `seed/{lib,framework}/frontend/src` -> changed FE package, consumers =
      products whose package.json lists it (a `@noctusai/lib` change also
      reaches `@noctusai/seed` dependents). ANYTHING ELSE under seed/
      (conftest, pyproject/requirements, package.json/lockfiles, vite
      factory, Dockerfiles, non-.py data, unparseable files) -> the WHOLE
      fleet, exactly as before: when unsure, never under-scope. Directly
      diffed products always keep their own gates. `scope["seed_fanout"]`
      records mode scoped|fleet and what was included/excluded, and a scoped
      run adds a warning (CI runs the full matrix). Gates run in parallel
      (`max_workers`, default cpu//2), results kept in spec order.
  `mcp/...`                                 -> `mcp_toolkit_tests:scoped`
      (2026-10-09): pytest over ONLY the affected test files — every
      changed `tests/test_*.py`, every test that imports a changed module
      (ast, any depth in the file), and `test_<module>[_*].py`. The full
      suite (~21 min, past the merged-tip time-box — every toolkit
      integrate was `incomplete`) runs as `mcp_toolkit_tests` only when
      shared test infra changed (conftest, settings, requirements, a
      non-test helper under tests/, any non-.py toolkit file); CI always
      runs it in full. A changed module NO test imports is surfaced as the
      `mcp_untested_change` entry (ran=False → `incomplete`), never a
      silent pass. `scripts/hooks/<name>.py` joins this bucket: its tests live
      in the toolkit suite and load the hook by path, so the tests whose text
      names the file are selected.
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

import ast
import functools
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from env_bootstrap import dotenv_residue, gate_subprocess_env, redact_secrets_in_text
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
_MCP_RE = re.compile(r"^(mcp/|scripts/hooks/[^/]+\.py$)")
_KB_DOC_RE = re.compile(
    r"^(KNOWLEDGE-BASE/|CLAUDE\.md$|CLAUDE/|\.claude/(agents|skills|commands)/|project-history/roadmaps/)"
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
    seed_files: list[str] = []
    mcp_touched = False
    mcp_files: list[str] = []
    doc_files: list[str] = []
    other_files: list[str] = []
    for f in files:
        m = _PRODUCT_RE.match(f)
        if m:
            products.add(m.group(1))
            continue
        if _SEED_FLEET_RE.match(f):
            seed_fleet_wide = True
            seed_files.append(f)
            continue
        if _MCP_RE.match(f):
            mcp_touched = True
            mcp_files.append(f)
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
        "seed_files": sorted(seed_files),
        "mcp": mcp_touched,
        "mcp_files": sorted(mcp_files),
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
        d.name for d in products_dir.iterdir() if d.is_dir() and not d.name.startswith(".")  # product-scope: all — raw list; callers filter_active (seed fan-out) or flag explicit requests
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


# ─── seed fan-out scoping (2026-10-09) ──────────────────────────────────────
# A seed/ change used to fan out to EVERY active product x (pytest + vite_build
# + e2e) — past the merged-tip time-box, so every seed integrate ended
# `incomplete`. `_seed_fanout_plan` narrows it to the products that can
# actually be affected, or returns None (= whole fleet) whenever it cannot
# PROVE a narrower set: when unsure, never under-scope. CI runs the full matrix.

#: package name -> (repo-relative package dir, seed pytest root)
_SEED_PY_PKGS = {
    "noctusai_lib": ("seed/lib/backend/noctusai_lib", "seed/lib/backend"),
    "noctusai_seed": ("seed/framework/backend/noctusai_seed", "seed/framework/backend"),
}
#: npm package -> (repo-relative src dir, seed vitest root)
_SEED_FE_PKGS = {
    "@noctusai/lib": ("seed/lib/frontend/src", "seed/lib/frontend"),
    "@noctusai/seed": ("seed/framework/frontend/src", "seed/framework/frontend"),
}
_FE_TEST_FILE_RE = re.compile(r"\.(test|spec)\.[jt]sx?$")
_SKIP_DIRS = frozenset({".venv", "venv", "node_modules", "__pycache__", ".git", "dist"})


def _py_files_under(base: Path):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                yield Path(dirpath) / fn


def _seed_module_index(root: Path) -> dict[str, Path]:
    """dotted module name -> file, for both seed python packages
    (`__init__.py` maps to its package)."""
    mods: dict[str, Path] = {}
    for pkg, (rel, _r) in _SEED_PY_PKGS.items():
        base = root / rel
        if not base.is_dir():
            continue
        for f in _py_files_under(base):
            parts = list(f.relative_to(base).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            mods[".".join([pkg, *parts])] = f
    return mods


def _is_type_checking_test(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _runtime_nodes(tree: ast.AST):
    """`ast.walk`, minus `if TYPE_CHECKING:` bodies — those imports never run,
    so they are not runtime dependencies (the `else:` branch still is)."""
    todo = [tree]
    while todo:
        node = todo.pop()
        yield node
        if isinstance(node, ast.If) and _is_type_checking_test(node.test):
            todo.extend(node.orelse)
            continue
        todo.extend(ast.iter_child_nodes(node))


def _seed_lazy_maps(mods: dict[str, Path]) -> dict[str, dict[str, str]]:
    """package -> {public name: providing module} for every seed package whose
    `__init__` is a PEP 562 lazy package (a module-level ``_LAZY_ATTRS`` dict
    literal of str -> str). `from pkg import name` then depends on the module
    that actually provides `name`, not on every module the package could load."""
    out: dict[str, dict[str, str]] = {}
    for name, f in mods.items():
        if f.name != "__init__.py":
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            raise _FallBack(f"unparseable seed module {f.name}")
        for node in tree.body:
            target = (
                node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1
                else node.target if isinstance(node, ast.AnnAssign) else None
            )
            if isinstance(target, ast.Name) and target.id == "_LAZY_ATTRS" and isinstance(
                node.value, ast.Dict
            ):
                mapping: dict[str, str] = {}
                for k, v in zip(node.value.keys, node.value.values):
                    if not (
                        isinstance(k, ast.Constant) and isinstance(k.value, str)
                        and isinstance(v, ast.Constant) and isinstance(v.value, str)
                    ):
                        raise _FallBack(f"non-literal _LAZY_ATTRS in {name}")
                    mapping[k.value] = v.value
                out[name] = mapping
    return out


def _file_import_deps(
    tree: ast.AST,
    known: set[str],
    own_pkg: str | None = None,
    lazy: dict[str, dict[str, str]] | None = None,
) -> set[str]:
    """Known seed modules a parsed file depends on. `own_pkg` = the dotted
    package a relative import resolves against (None = no relative imports).
    Importing `a.b.c` executes `a` and `a.b` too, so every existing prefix of
    each imported name counts; `from a.b import c` also tries `a.b.c`.
    `lazy` = `_seed_lazy_maps`: `from lazy_pkg import X` depends on the module
    providing X; a bare `import lazy_pkg` (attribute access we cannot see)
    conservatively depends on every module the package can load."""
    lazy = lazy or {}
    names: set[str] = set()
    for node in _runtime_nodes(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name)
                if a.name in lazy:
                    names.update(lazy[a.name].values())
                    names.update(k for k in known if k.startswith(a.name + "."))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if own_pkg is None:
                    continue
                parts = own_pkg.split(".")
                if node.level - 1 > len(parts) - 1:
                    continue
                base_parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join(base_parts + ([node.module] if node.module else []))
            elif node.module:
                base = node.module
            else:
                continue
            names.add(base)
            names.update(f"{base}.{a.name}" for a in node.names if a.name != "*")
            if base in lazy:
                for a in node.names:
                    if a.name == "*":  # star-import resolves every public name
                        names.update(lazy[base].values())
                    elif a.name in lazy[base]:
                        names.add(lazy[base][a.name])
    deps: set[str] = set()
    for n in names:
        parts = n.split(".")
        for i in range(1, len(parts) + 1):
            cand = ".".join(parts[:i])
            if cand in known:
                deps.add(cand)
    return deps


def _seed_py_graph(root: Path, mods: dict[str, Path]) -> dict[str, set[str]]:
    known = set(mods)
    lazy = _seed_lazy_maps(mods)
    graph: dict[str, set[str]] = {}
    for name, f in mods.items():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            raise _FallBack(f"unparseable seed module {f.name}")
        own_pkg = name if f.name == "__init__.py" else name.rpartition(".")[0]
        graph[name] = _file_import_deps(tree, known, own_pkg or None, lazy) - {name}
    return graph


class _FallBack(Exception):
    """The plan cannot be proven narrower than the fleet."""


def _product_py_deps(
    root: Path, slug: str, known: set[str], lazy: dict[str, dict[str, str]] | None = None
) -> set[str]:
    backend = root / "products" / slug / "backend"
    deps: set[str] = set()
    if not backend.is_dir():
        return deps
    for f in _py_files_under(backend):
        try:
            text = f.read_text(encoding="utf-8")
            if "noctusai" not in text:
                continue  # cannot import a seed package (cheap pre-filter)
            tree = ast.parse(text)
        except (SyntaxError, UnicodeDecodeError, OSError):
            raise _FallBack(f"unparseable product file {slug}/{f.name}")
        deps |= _file_import_deps(tree, known, None, lazy)
    return deps


def _product_fe_deps(root: Path, slug: str) -> set[str]:
    pj = _pkg_json(root / "products" / slug / "frontend")
    return set((pj.get("dependencies") or {})) | set((pj.get("devDependencies") or {}))


def _seed_fanout_plan(root: Path, seed_files: list[str]) -> dict[str, Any] | None:
    """Narrow a seed/ diff to the consumers it can reach, or None (= whole
    fleet). See the "seed fan-out scoping" comment above and the module
    docstring's SCOPE DERIVATION."""
    try:
        return _seed_fanout_plan_inner(root, seed_files)
    except _FallBack:
        return None


def _seed_fanout_plan_inner(root: Path, seed_files: list[str]) -> dict[str, Any] | None:
    py_roots: set[str] = set()
    fe_roots: set[str] = set()
    changed_py: set[str] = set()   # candidate module names (resolved below)
    changed_fe: set[str] = set()
    for f in seed_files:
        if f.endswith(".md"):
            continue
        matched = False
        for root_rel in ("seed/lib/backend", "seed/framework/backend"):
            if f.startswith(root_rel + "/tests/"):
                py_roots.add(root_rel)
                matched = True
        for root_rel in _SEED_FE_PKGS.values():
            if f.startswith(root_rel[1] + "/tests/"):
                fe_roots.add(root_rel[1])
                matched = True
        if matched:
            continue
        for pkg, (rel, _r) in _SEED_PY_PKGS.items():
            if f.startswith(rel + "/") and f.endswith(".py"):
                parts = f[len(rel) + 1:-3].split("/")
                if parts[-1] == "__init__":
                    parts = parts[:-1]
                changed_py.add(".".join([pkg, *parts]))
                matched = True
        if matched:
            continue
        for pkg, (rel, vroot) in _SEED_FE_PKGS.items():
            if f.startswith(rel + "/"):
                if "/__tests__/" in f or "/tests/" in f or _FE_TEST_FILE_RE.search(f):
                    fe_roots.add(vroot)
                else:
                    changed_fe.add(pkg)
                matched = True
                break
        if not matched:
            return None  # conftest / pyproject / package.json / factory / docker / ...

    consumers_py: set[str] = set()
    affected: set[str] = set()
    if changed_py:
        mods = _seed_module_index(root)
        known = set(mods)
        # A deleted/renamed module is not in the index — nothing to anchor on.
        changed_known = {m for m in changed_py if m in known}
        if changed_known != changed_py:
            return None
        graph = _seed_py_graph(root, mods)
        lazy = _seed_lazy_maps(mods)
        affected = set(changed_known)
        grew = True
        while grew:
            grew = False
            for m, deps in graph.items():
                if m not in affected and deps & affected:
                    affected.add(m)
                    grew = True
        for m in affected:
            py_roots.add(_SEED_PY_PKGS[m.split(".", 1)[0]][1])
        for slug in _all_product_slugs(root):
            if _product_py_deps(root, slug, known, lazy) & affected:
                consumers_py.add(slug)

    consumers_fe: set[str] = set()
    if changed_fe:
        # @noctusai/seed bundles @noctusai/lib: a lib change reaches both.
        reach = set(changed_fe)
        if "@noctusai/lib" in changed_fe:
            reach.add("@noctusai/seed")
            fe_roots.add(_SEED_FE_PKGS["@noctusai/lib"][1])
            fe_roots.add(_SEED_FE_PKGS["@noctusai/seed"][1])
        if "@noctusai/seed" in changed_fe:
            fe_roots.add(_SEED_FE_PKGS["@noctusai/seed"][1])
        for slug in _all_product_slugs(root):
            if _product_fe_deps(root, slug) & reach:
                consumers_fe.add(slug)

    return {
        "seed_py": bool(py_roots),
        "seed_fe": bool(fe_roots),
        "py_roots": sorted(py_roots),
        "fe_roots": sorted(fe_roots),
        "py_products": consumers_py,
        "fe_products": consumers_fe,
        "python_modules": sorted(affected) if changed_py else [],
        "changed_python_modules": sorted(changed_py),
        "frontend_packages": sorted(changed_fe),
    }


# ─── mcp toolkit gate scoping (2026-10-09) ──────────────────────────────────
_MCP_PKG = "mcp/noctusai/"
#: Changes here can affect ANY toolkit test → full suite.
_MCP_FULL_SUITE_FILES = frozenset({
    "tests/conftest.py", "tests/__init__.py", "settings.py",
    "requirements.txt", "pyproject.toml",
})
#: Docs with no test surface.
_MCP_NO_TEST_SUFFIXES = (".md",)
_COMPLIANCE_REL = "mcp/noctusai/tools/noctus/dev/compliance.py"
# Keeper-registration meta-tests: fast, and the ones a new `check_*` breaks.
_KEEPER_META_TESTS = (
    "mcp/noctusai/tests/test_compliance.py::TestCheckDetectorHasRegressionTest",
)


def _mcp_module_name(rel: str) -> str:
    """`tools/noctus/dev/x.py` → `tools.noctus.dev.x` (tests put `mcp/noctusai`
    on sys.path); a package `__init__.py` maps to the package."""
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imported_names(tree: ast.AST) -> set[str]:
    """Every dotted name a file imports, anywhere (lazy in-function imports
    included). `from a.b import c` yields both `a.b` and `a.b.c` — `c` may be
    a submodule (`from tools.noctus.dev import gate_sweep`)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def _mcp_scoped_test_files(
    root: Path, mcp_files: list[str]
) -> tuple[list[str], list[str]] | None:
    """Affected toolkit test files for `mcp_files`, or None = run the full suite.

    Returns ``(tests, untested_modules)``: repo-relative test paths, and the
    changed modules no test imports (surfaced, never silently passed)."""
    pkg_dir = root / _MCP_PKG
    changed_tests: set[str] = set()
    changed_mods: dict[str, str] = {}
    hook_files: list[str] = []
    data_files: list[str] = []
    for f in mcp_files:
        if f.startswith("scripts/hooks/"):
            hook_files.append(f)  # tested from the toolkit suite, loaded by path
            continue
        if not f.startswith(_MCP_PKG):
            return None
        rel = f[len(_MCP_PKG):]
        if rel.endswith(_MCP_NO_TEST_SUFFIXES):
            continue
        if rel.startswith("tests/") and not rel.endswith(".py"):
            data_files.append(f)  # a fixture/baseline: the tests that name it
            continue
        if rel in _MCP_FULL_SUITE_FILES or not rel.endswith(".py"):
            return None
        if rel.startswith("tests/"):
            if not Path(rel).name.startswith("test_"):
                return None  # a shared test helper — anything may use it
            if (root / f).exists():  # a deleted test has nothing to run
                changed_tests.add(f)
            continue
        changed_mods[_mcp_module_name(rel)] = rel

    affected = set(changed_tests)
    covered: set[str] = set()
    if changed_mods:
        stems = {Path(rel).stem: mod for mod, rel in changed_mods.items()}
        for test in sorted((pkg_dir / "tests").rglob("test_*.py")):
            rel_test = str(test.relative_to(root))
            stem_hit = next(
                (m for st, m in stems.items()
                 if test.stem == f"test_{st}" or test.stem.startswith(f"test_{st}_")),
                None,
            )
            try:
                imported = _imported_names(ast.parse(test.read_text(encoding="utf-8")))
            except (SyntaxError, UnicodeDecodeError):
                affected.add(rel_test)  # can't tell — run it
                continue
            hits = [m for m in changed_mods if m in imported]
            if stem_hit:
                hits.append(stem_hit)
            if hits:
                affected.add(rel_test)
                covered.update(hits)
    untested = sorted(changed_mods[m] for m in changed_mods if m not in covered)
    for hook in [*hook_files, *data_files]:
        name = Path(hook).name
        hits = [str(t.relative_to(root)) for t in sorted((pkg_dir / "tests").rglob("test_*.py"))
                if name in t.read_text(encoding="utf-8", errors="replace")]
        affected.update(hits)
        if not hits:
            untested.append(hook)
    return sorted(affected), sorted(untested)


def _build_gate_specs(root: Path, scope: dict[str, Any]) -> list[GateSpec]:
    py = resolve_test_python()
    specs: list[GateSpec] = []

    if scope["seed_fleet_wide"]:
        all_slugs = _all_product_slugs(root)
        active_slugs = filter_active(all_slugs, root=root)
        scope["skipped_asleep"] = sorted(set(all_slugs) - set(active_slugs))
        plan = _seed_fanout_plan(root, scope.get("seed_files", []))
        if plan is None:
            # Whole fleet. A seed change fans out to every product's own
            # gates — but only the ACTIVE (awake) ones. An asleep product
            # (dormant_slugs, per deploy/fleet/active-scope.txt) is surfaced
            # in `skipped_asleep`, never dropped silently (see
            # product_scope.py's module docstring).
            scope["seed_fanout"] = {"mode": "fleet", "reason": "seed change not provably narrower than the fleet"}
            specs.extend(_seed_gate_specs(root, py))
            for slug in active_slugs:
                specs.extend(_product_gate_specs(root, slug, py))
        else:
            direct = set(scope["products"])
            for spec in _seed_gate_specs(root, py):
                rel = spec.gate.split(":", 1)[1]
                if spec.gate.startswith("pytest:") and rel in plan["py_roots"]:
                    specs.append(spec)
                elif spec.gate.startswith("vitest:") and rel in plan["fe_roots"]:
                    specs.append(spec)
            included_py: set[str] = set()
            included_fe: set[str] = set()
            for slug in active_slugs:
                for spec in _product_gate_specs(root, slug, py):
                    kind = spec.gate.split(":", 1)[0]
                    wanted = (
                        slug in direct
                        or (kind == "pytest" and slug in plan["py_products"])
                        or (kind in ("vite_build", "e2e") and slug in plan["fe_products"])
                    )
                    if wanted:
                        specs.append(spec)
                        (included_py if kind == "pytest" else included_fe).add(slug)
            excluded = sorted(set(active_slugs) - included_py - included_fe)
            scope["seed_fanout"] = {
                "mode": "scoped",
                "reason": "seed diff resolved to a provable consumer set",
                "python_modules": plan["python_modules"],
                "changed_python_modules": plan["changed_python_modules"],
                "frontend_packages": plan["frontend_packages"],
                "seed_pytest_roots": plan["py_roots"],
                "seed_vitest_roots": plan["fe_roots"],
                "products_pytest": sorted(included_py),
                "products_frontend": sorted(included_fe),
                "excluded_products": excluded,
            }
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

    if scope["mcp"] and _COMPLIANCE_REL in scope.get("mcp_files", []):
        # Keeper gates go FIRST: they are seconds-scale, and a shared
        # wall-clock budget (integrate's merged-tip check) must measure them
        # before any long suite can starve them. 2026-10-10: a new keeper
        # landed whose detector-registration meta-test and fleet baseline
        # were both only inside suites that timed out unmeasured.
        specs[:0] = [
            GateSpec("keeper_meta", [py, "-m", "pytest", *_KEEPER_META_TESTS, "-q"], root),
            GateSpec("keeper_delta", [py, "mcp/noctusai/cli.py", "--check-keeper-delta",
                                      "--keeper-delta-base-ref", scope.get("base_ref", "origin/dev"),
                                      "--worktree-path", str(root)], root),
        ]

    if scope["mcp"]:
        scoped = _mcp_scoped_test_files(root, scope.get("mcp_files", []))
        if scoped is None:
            specs.append(
                GateSpec("mcp_toolkit_tests", [py, "-m", "pytest", "mcp/noctusai/tests/", "-q"], root)
            )
        else:
            tests, untested = scoped
            scope["mcp_scoped_tests"] = tests
            scope["mcp_untested_modules"] = untested
            if tests:
                specs.append(
                    GateSpec("mcp_toolkit_tests:scoped", [py, "-m", "pytest", *tests, "-q"], root)
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
    all (timeout, missing executable) — never conflated with `0`.

    🔴 ENV HYGIENE (2026-09-27; value scrub 2026-10-09) — runs with `gate_subprocess_env()`
    (= `sanitize_subprocess_env()` + a scrub of every .env-identical value),
    NOT a bare inherited `os.environ`. This process (the MCP server / CLI)
    may have loaded real secrets from `.env` via `env_bootstrap`; CI runs
    these exact suites from a scrubbed `env -i` (see `.github/workflows/
    test.yml`'s Seed/Tooling Tests jobs), so an inherited-secrets
    subprocess is a PERMANENT false-red for any test asserting "unset env
    -> X" — the harness, not the code (`KB § PATTERNS/common/methodology-
    execution-discipline.md` § 7). The `summary` this returns is also
    passed through `redact_secrets_in_text` — a failing assertion line can
    otherwise copy a live credential straight into an MCP tool result. See
    `mcp/noctusai/env_bootstrap.py`'s module docstring for the full
    incident."""
    start = time.time()
    try:
        proc = subprocess.run(
            spec.argv, cwd=str(spec.cwd), capture_output=True, text=True, timeout=timeout,
            env=gate_subprocess_env(Path(spec.cwd)),
        )
    except subprocess.TimeoutExpired:
        return None, f"timeout after {timeout}s", time.time() - start
    except OSError as exc:
        return None, f"could not run {spec.argv[0]!r}: {exc}", time.time() - start
    duration = time.time() - start
    combined = (proc.stdout or "") + (proc.stderr or "")
    summary = (
        redact_secrets_in_text(_last_meaningful_line(combined))
        if combined.strip() else "(no output)"
    )
    return proc.returncode, summary, duration, combined


def _run_gates(
    specs: list[GateSpec],
    run_gate: Callable[[GateSpec], GateRunResult],
    env_residue: list[str] | None = None,
    max_workers: int = 1,
) -> list[dict[str, Any]]:
    """Preflight, then run, then classify — in that order.

    A gate whose preconditions are unmet is NOT RUN. That is the point: an
    unrun gate has no exit code to be mistaken for a verdict about the
    code. It is recorded `ran=False` with `harness_invalid` naming what is
    missing and how to fix it.

    Gates run on up to `max_workers` threads (each is its own subprocess, so
    threads only wait); results are returned in SPEC ORDER regardless."""
    workers = max(1, min(max_workers, len(specs) or 1))
    if workers == 1:
        return [_run_one_gate(spec, run_gate, env_residue) for spec in specs]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda sp: _run_one_gate(sp, run_gate, env_residue), specs))


def _run_one_gate(
    spec: GateSpec,
    run_gate: Callable[[GateSpec], GateRunResult],
    env_residue: list[str] | None,
) -> dict[str, Any]:
    if env_residue:
        # The developer's `.env` is still in the gate env (2026-10-09:
        # merged-tip pytest false-redded 4 "unset key -> X" tests). The
        # result would judge the `.env`, not the code — do not run it.
        return {
            "gate": spec.gate,
            "ran": False,
            "exit_code": None,
            "summary": (
                "HARNESS INVALID — gate NOT run: the gate env still carries "
                f"{len(env_residue)} key(s) with the repo .env's exact values"
            ),
            "duration_s": 0.0,
            "harness_invalid": [{
                "precondition": "env_free_of_dotenv",
                "missing_path": ", ".join(env_residue),
                "remedy": (
                    "unset these in the launching shell (they were exported from "
                    ".env, e.g. `set -a; . .env`) or run from a clean shell — CI "
                    "runs these suites without .env"
                ),
            }],
        }
    unmet = [p for p in spec.preconditions if not p.path.exists()]
    if unmet:
        return {
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
        }

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
            # `matched_line` is sliced from the RAW combined stdout/
            # stderr (see `harness_signatures.harness_suspect`), so it
            # is a second leak surface independent of `summary` — same
            # redaction, same reason (module docstring, 2026-09-27).
            suspect["matched_line"] = redact_secrets_in_text(suspect["matched_line"])
            entry["harness_suspect"] = suspect
    return entry


def _named_gate_specs(root: Path, gate_names: list[str]) -> tuple[list[GateSpec], list[str]]:
    """Specs for exactly `gate_names` (product `pytest:/vite_build:/e2e:<slug>`
    and seed `pytest:/vitest:<rel>` gates) built by the SAME spec builders
    the sweep uses — no second definition of what a gate runs. Returns
    (specs, unknown) where `unknown` are names with no spec in `root`."""
    py = resolve_test_python()
    wanted = set(gate_names)
    pool: dict[str, GateSpec] = {sp.gate: sp for sp in _seed_gate_specs(root, py)}
    for name in wanted:
        if name in pool or ":" not in name:
            continue
        kind, key = name.split(":", 1)
        if kind in ("pytest", "vite_build", "e2e"):
            for sp in _product_gate_specs(root, key, py):
                pool.setdefault(sp.gate, sp)
    specs = [pool[n] for n in gate_names if n in pool]
    return specs, [n for n in gate_names if n not in pool]


def run_gates_named(
    repo_root: str,
    gate_names: list[str],
    timeout: int = 300,
    run_gate: Callable[[GateSpec], GateRunResult] | None = None,
    max_workers: int | None = None,
) -> dict[str, Any]:
    """Run ONLY the named gates in `repo_root` (no diff, no scope derivation)
    and return `{gates, unknown}` with the sweep's own per-gate entry shape
    (ran / exit_code / harness_invalid / harness_suspect). Gate-level
    granularity: a gate is rerun whole, not narrowed to failing test ids.
    Used by task_branch's merged-tip dev baseline."""
    root = Path(repo_root)
    specs, unknown = _named_gate_specs(root, gate_names)
    runner = run_gate or functools.partial(_default_run_gate, timeout=timeout)
    env_residue = dotenv_residue(gate_subprocess_env(root), root)
    workers = max_workers if max_workers else max(1, (os.cpu_count() or 2) // 2)
    return {"gates": _run_gates(specs, runner, env_residue, max_workers=workers),
            "unknown": unknown}


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
    max_workers: int | None = None,
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
        max_workers: gate parallelism (default max(1, cpu_count//2)); results
            stay in spec order.

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
    scope["base_ref"] = base_ref
    specs = _build_gate_specs(root, scope)
    runner = run_gate or functools.partial(_default_run_gate, timeout=timeout)

    # Measured against what `_default_run_gate` actually hands its subprocess
    # (provenance strip + .env-value scrub) — a backstop that only fires if the
    # scrub ever regresses; the scrub itself makes it empty by construction.
    env_residue = dotenv_residue(gate_subprocess_env(root), root)
    workers = max_workers if max_workers else max(1, (os.cpu_count() or 2) // 2)
    gates = _run_gates(specs, runner, env_residue, max_workers=workers)

    fanout = scope.get("seed_fanout") or {}
    if fanout.get("mode") == "scoped":
        warnings.append(
            "seed fan-out SCOPED to "
            f"pytest={fanout['products_pytest']} frontend={fanout['products_frontend']} "
            f"(excluded: {len(fanout['excluded_products'])} active product(s)) — "
            "CI runs the full matrix"
        )

    if scope.get("mcp_untested_modules"):
        untested = scope["mcp_untested_modules"]
        gates.append({
            "gate": "mcp_untested_change",
            "ran": False,
            "exit_code": None,
            "summary": (
                f"{len(untested)} changed toolkit module(s) no test imports: "
                f"{untested[:20]}" + (" …" if len(untested) > 20 else "")
                + " — only CI's full suite exercises them (indirectly, if at all)"
            ),
            "duration_s": 0.0,
        })

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
    "run_gates_named",
    "register",
    "_derive_scope",
    "_changed_files",
    "_build_gate_specs",
    "_default_run_gate",
    "_verdict",
    "_porcelain_paths",
    "_all_product_slugs",
]
