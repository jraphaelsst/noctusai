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
import sys
from pathlib import Path

import pytest

# MCP root (parent of tests/)
_MCP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_MCP_ROOT))

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
