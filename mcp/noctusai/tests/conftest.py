"""Shared fixtures for the mcp/noctusai suite.

The `domain_product` fixture is the registry-derived replacement for the
hardcoded `mailing` slug that several tests used as their "a real domain
product" anchor. `mailing` was absorbed into `social-wiring/email_marketing`
and deleted in the social-wiring-absorption Wave-4 teardown; the mcp test
matrix is a derived surface the teardown grep missed. Resolving from the live
registry instead of freezing a slug literal is the hardcoded-product-slug-set
rule applied (feedback_hardcoded_product_slug_set_keeper) and closes the
dangling-deleted-product gap (feedback_dangling_deleted_product_path) for this
surface permanently — no future product deletion can re-redden these tests.
"""
import os
import sys
from pathlib import Path

import pytest

# The ledger store (`tools.noctus.dev._ledger_store`) defaults to the REAL
# store — git plumbing that pushes to origin/ledgers. The suite must never push
# anywhere, so it is pinned to the file-backed Fake for every test (assigned,
# not setdefault: a shell that exported `git` must not leak into the suite).
# Tests of the Real store build a `GitLedgerStore` on a temp bare repo directly.
os.environ["NOCTUS_LEDGER_STORE"] = "fake"

# MCP root (parent of tests/)
_MCP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_MCP_ROOT))

# The repo-root `dev_team` engine (imported lazily by `noctus.team.*` tools).
# Suite-wide, not per-file: `test_rollups.py` exercised the same imports but
# only passed when `test_team_tools.py` — which used to add this path itself —
# had run first in the same process. CI sharding (2026-09-21) broke that
# accidental order.
_DEV_TEAM_SRC = _MCP_ROOT.parents[1] / "dev_team" / "src"
if str(_DEV_TEAM_SRC) not in sys.path:
    sys.path.insert(0, str(_DEV_TEAM_SRC))

# When running from a git worktree the venv-installed noctusai_lib uses an
# editable-install MetaPathFinder that hardcodes the PRIMARY checkout path.
# That finder takes priority over sys.path, so a simple sys.path.insert can't
# override it. In a worktree we need to surgically redirect noctusai_lib to
# point at the local (edited) copy instead.
#
# Strategy: find the editable finder, patch its MAPPING to point at the
# worktree's seed lib, then evict any already-cached noctusai_lib modules so
# the next import picks up the worktree version. Only applied when a
# worktree seed lib exists AND it differs from the finder's current path.
_WORKTREE_ROOT = _MCP_ROOT.parent.parent  # .claude/worktrees/<name>
_WORKTREE_SEED_LIB = _WORKTREE_ROOT / "seed" / "lib" / "backend"

if _WORKTREE_SEED_LIB.exists():
    # The editable-install MetaPathFinder resolves noctusai_lib to the PRIMARY
    # checkout, not this worktree. For git-worktree isolation the two trees have
    # DIFFERENT files on disk (the worktree has our edits; primary does not).
    #
    # Strategy: evict ALL cached noctusai_lib.* modules from sys.modules, then
    # prepend the worktree seed lib to sys.path. The next import of any
    # noctusai_lib.* module picks up the worktree copy. The editable-install
    # MetaPathFinder only wins when sys.path doesn't have a plain-directory
    # entry that already satisfies the import — prepending takes priority.
    #
    # This replaces the surgical per-module redirect that used importlib.util
    # directly (which failed on relative imports inside build.py because
    # spec_from_file_location doesn't set the package context for relative
    # imports to resolve).
    _to_evict = [k for k in sys.modules if k.startswith("noctusai_lib")]
    for _k in _to_evict:
        del sys.modules[_k]
    if str(_WORKTREE_SEED_LIB) not in sys.path:
        sys.path.insert(0, str(_WORKTREE_SEED_LIB))

    # Legacy per-module redirect kept for extract_mined (the original worktree
    # change) as a belt-and-suspenders check — it's now a no-op since the
    # evict+prepend above handles it, but keep to avoid regressions.
    import importlib.util as _ilu
    _wt_extract_mined_path = (
        _WORKTREE_SEED_LIB / "noctusai_lib" / "graph" / "extract_mined.py"
    )
    if _wt_extract_mined_path.exists():
        _spec = _ilu.spec_from_file_location(
            "noctusai_lib.graph.extract_mined",
            str(_wt_extract_mined_path),
        )
        if _spec and _spec.loader:
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            sys.modules["noctusai_lib.graph.extract_mined"] = _mod

    # W3: noctusai_lib.components is a new package (not in the primary checkout).
    # Force-load both the package __init__ and validation_signal from the worktree.
    _wt_components_dir = _WORKTREE_SEED_LIB / "noctusai_lib" / "components"
    if _wt_components_dir.exists() and "noctusai_lib.components" not in sys.modules:
        # Register the package first (its __init__.py depends on validation_signal).
        _vs_path = _wt_components_dir / "validation_signal.py"
        _init_path = _wt_components_dir / "__init__.py"

        if _vs_path.exists():
            # Load validation_signal first so the __init__ import works.
            _vs_spec = _ilu.spec_from_file_location(
                "noctusai_lib.components.validation_signal",
                str(_vs_path),
            )
            if _vs_spec and _vs_spec.loader:
                _vs_mod = _ilu.module_from_spec(_vs_spec)
                sys.modules["noctusai_lib.components.validation_signal"] = _vs_mod
                _vs_spec.loader.exec_module(_vs_mod)

        if _init_path.exists():
            _pkg_spec = _ilu.spec_from_file_location(
                "noctusai_lib.components",
                str(_init_path),
                submodule_search_locations=[str(_wt_components_dir)],
            )
            if _pkg_spec and _pkg_spec.loader:
                _pkg_mod = _ilu.module_from_spec(_pkg_spec)
                sys.modules["noctusai_lib.components"] = _pkg_mod
                _pkg_spec.loader.exec_module(_pkg_mod)

from tools.noctus.dev.products import list_products


def resolve_domain_product() -> str:
    """The alphabetically-first non-seed product that has a backend and ≥1
    domain router, resolved from the live product registry."""
    for p in sorted(list_products(), key=lambda d: d["name"]):
        if p["name"] != "seed" and p.get("has_backend") and p.get("routers"):
            return p["name"]
    raise AssertionError("no domain product with backend routers in registry")


@pytest.fixture(scope="session")
def domain_product() -> str:
    return resolve_domain_product()


@pytest.fixture
def ledger_repo(tmp_path, monkeypatch):
    """A REAL ledger store on a temp bare repo — never the network.

    Builds ``origin.git`` (bare, `dev` = HEAD) + a clone whose
    ``project-history/`` holds the legacy dev copies, bootstraps
    ``origin/ledgers`` from them, then switches THIS test to the Real store
    (``NOCTUS_LEDGER_STORE=git``) with ``settings.LEDGER_ROOT`` pointed at the
    clone. Yields ``(bare, clone, show)`` where ``show(name)`` returns the
    ledger's content on the bare remote's ``ledgers`` branch ("" if absent).
    """
    import subprocess as _sp

    import settings as _settings
    from tools.noctus.dev import _ledger_store as _ls

    def g(cwd, *a):
        r = _sp.run(["git", *a], cwd=str(cwd), capture_output=True, text=True)
        assert r.returncode == 0, f"git {a}: {r.stderr}"
        return r.stdout

    bare = tmp_path / "origin.git"
    _sp.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    clone = tmp_path / "primary"
    _sp.run(["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True)
    g(clone, "config", "user.email", "t@example.com")
    g(clone, "config", "user.name", "t")
    (clone / "project-history").mkdir()
    (clone / "project-history" / "README.md").write_text("ledgers\n")
    g(clone, "add", "project-history")
    g(clone, "commit", "-qm", "init")
    g(clone, "push", "-q", "origin", "HEAD:refs/heads/dev")
    g(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    g(clone, "fetch", "-q", "origin")
    boot = _ls.GitLedgerStore(repo_root=clone, backoff_s=0).bootstrap(
        {"README.md": "test ledgers\n"}, message="seed")
    assert boot["ok"], boot
    monkeypatch.setenv(_ls.ENV_MODE, _ls.MODE_GIT)
    monkeypatch.setattr(_settings, "LEDGER_ROOT", clone)

    def show(name: str) -> str:
        r = _sp.run(["git", "show", f"refs/heads/ledgers:{name}"], cwd=str(bare),
                    capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""

    yield bare, clone, show


@pytest.fixture(autouse=True)
def _isolate_branch_tree_dev_copy(tmp_path, monkeypatch):
    """Point `branch_pointer.LEDGER_PATH` at an empty per-test path.

    Since 2026-09-24 every branch-tree read is the dual-read (origin/dev's
    copy ∪ the ledger store) and the suite's Fake store is backed by
    `LEDGER_PATH` — which is the REAL primary checkout's ledger unless a test
    points it elsewhere. Without this, any test that reaches
    `branch_pointer.query` (the staleness guards, cleanup, the stale-pointer
    keeper) would silently merge production pointers into its fixture.
    Tests that need a local ledger still override it themselves."""
    from tools.noctus.dev import branch_pointer as _bp
    monkeypatch.setattr(_bp, "LEDGER_PATH", tmp_path / "_isolated-branch-tree" / "branch-tree.ndjson")
