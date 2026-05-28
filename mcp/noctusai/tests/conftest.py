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
    # Strategy: force-load the worktree's noctusai_lib.graph.extract_mined
    # directly via importlib and register it in sys.modules OVER the primary
    # copy. This gives tests the worktree's new symbols without disturbing any
    # other part of the import system.
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
