"""Tests for `noctusai_lib.testing.purge_shadowing_editable_finders`.

Five high-value scenarios covering the parallel-worktree shadow-purge contract:

(a) class-MAPPING finder pointing OUTSIDE local_root → REMOVED;
(b) module-MAPPING finder (pip PEP-660 shape) pointing OUTSIDE local_root → REMOVED;
(c) finder bound to a different worktree → PURGED;
(d) finder bound to the local worktree → PRESERVED;
(e) idempotency — calling twice in one process is safe and a no-op the second time.

Each test snapshots and restores `sys.meta_path` + `sys.modules` so
side-effects do not leak between tests.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from noctusai_lib.testing import purge_shadowing_editable_finders


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_meta_path():
    """Snapshot/restore sys.meta_path + sys.modules around each test.

    Tests intentionally mutate both as part of the helper's contract; this
    keeps the rest of the test session clean.
    """
    saved_meta = list(sys.meta_path)
    saved_mods = {k: v for k, v in sys.modules.items()}
    yield
    sys.meta_path[:] = saved_meta
    # Restore exactly: drop any added entries, restore any removed ones.
    for k in list(sys.modules):
        if k not in saved_mods:
            del sys.modules[k]
    for k, v in saved_mods.items():
        sys.modules[k] = v


def _make_class_mapping_finder(target: str):
    """Build a class with a class-level ``MAPPING`` attribute pointing at ``target``."""

    class _ClassMappingFinder:
        MAPPING = {"noctusai_lib": target}

    return _ClassMappingFinder


def _make_module_mapping_finder(target: str, mod_name: str):
    """Mimic pip's PEP-660 shape: class with no MAPPING, MAPPING on the *module*.

    Returns the class. Side-effect: registers the synthetic module in
    ``sys.modules[mod_name]`` so ``finder.__module__`` resolves correctly.
    """
    synthetic_mod = types.ModuleType(mod_name)
    synthetic_mod.MAPPING = {"noctusai_lib": target}
    sys.modules[mod_name] = synthetic_mod

    class _ModuleMappingFinder:
        # __module__ is auto-populated by Python at class creation time
        # (== current module of definition). Override to point at our
        # synthetic module so the helper's `finder.__module__` lookup hits
        # `sys.modules[mod_name]`.
        pass

    _ModuleMappingFinder.__module__ = mod_name
    return _ModuleMappingFinder


# ─── Tests ──────────────────────────────────────────────────────────────────


def test_class_mapping_finder_outside_local_is_removed(isolated_meta_path, tmp_path):
    """(a) Class-MAPPING finder pointing OUTSIDE local_root is dropped."""
    local_lib = tmp_path / "local_worktree" / "seed" / "lib" / "backend"
    local_lib.mkdir(parents=True)
    foreign_lib = tmp_path / "other_worktree" / "seed" / "lib" / "backend" / "noctusai_lib"
    foreign_lib.mkdir(parents=True)

    finder = _make_class_mapping_finder(str(foreign_lib))
    sys.meta_path.append(finder)
    assert finder in sys.meta_path

    purge_shadowing_editable_finders(local_lib)

    assert finder not in sys.meta_path, (
        "class-MAPPING finder pointing outside local_lib must be dropped"
    )


def test_module_mapping_finder_outside_local_is_removed(isolated_meta_path, tmp_path):
    """(b) Module-MAPPING finder (pip PEP-660 shape) pointing OUTSIDE local_root is dropped.

    THIS is the regression test for the bug PF Engineer A surfaced —
    pre-fix, `getattr(finder, "MAPPING", None)` against the class returned
    None and the finder was kept. Post-fix, the helper falls through to
    `sys.modules[finder.__module__].MAPPING` and drops it.
    """
    local_lib = tmp_path / "local_worktree" / "seed" / "lib" / "backend"
    local_lib.mkdir(parents=True)
    foreign_lib = tmp_path / "other_worktree" / "seed" / "lib" / "backend" / "noctusai_lib"
    foreign_lib.mkdir(parents=True)

    mod_name = "__editable___noctusai_lib_test_module_mapping_finder"
    finder = _make_module_mapping_finder(str(foreign_lib), mod_name)
    sys.meta_path.append(finder)
    assert finder in sys.meta_path

    purge_shadowing_editable_finders(local_lib)

    assert finder not in sys.meta_path, (
        "module-MAPPING finder (pip PEP-660 shape) pointing outside local_lib must be dropped"
    )


def test_finder_pointing_at_different_worktree_is_purged(isolated_meta_path, tmp_path):
    """(c) Finder bound to a *different* worktree is purged.

    Variant of (a)/(b) emphasizing the worktree-shadow scenario: the
    finder's noctusai_lib path resolves under a sibling worktree's
    seed/lib, not under the local worktree's seed/lib.
    """
    local_root = tmp_path / "noctusai-worktrees" / "branch-A" / "seed" / "lib" / "backend"
    local_root.mkdir(parents=True)
    sibling_root = (
        tmp_path / "noctusai-worktrees" / "branch-B" / "seed" / "lib" / "backend" / "noctusai_lib"
    )
    sibling_root.mkdir(parents=True)

    finder = _make_class_mapping_finder(str(sibling_root))
    sys.meta_path.append(finder)

    purge_shadowing_editable_finders(local_root)

    assert finder not in sys.meta_path, (
        "finder bound to a sibling worktree must be purged"
    )


def test_finder_pointing_at_local_worktree_is_preserved(isolated_meta_path, tmp_path):
    """(d) Finder bound to the LOCAL worktree's lib is preserved.

    The helper drops finders pointing OUTSIDE local_lib_root; finders
    pointing INSIDE local_lib_root must stay (they are the legitimate
    editable install for THIS worktree).
    """
    local_root = tmp_path / "local_worktree" / "seed" / "lib" / "backend"
    local_root.mkdir(parents=True)
    local_lib_pkg = local_root / "noctusai_lib"
    local_lib_pkg.mkdir(parents=True)

    finder = _make_class_mapping_finder(str(local_lib_pkg))
    sys.meta_path.append(finder)

    purge_shadowing_editable_finders(local_root)

    assert finder in sys.meta_path, (
        "finder bound to the LOCAL worktree must be preserved"
    )


def test_idempotent_double_call_is_safe(isolated_meta_path, tmp_path):
    """(e) Calling twice is safe — no AttributeError, no double-removal.

    Second call should be a no-op (shadowing finder already gone after
    the first call); cached `noctusai_lib*` modules already cleared.

    Implementation note: the surrounding test session may already have a
    real pip-editable `noctusai_lib` finder in `sys.meta_path` (pointing
    at whichever worktree owns the editable install). The helper will
    drop that one too on the first call. We compare *first call after*
    vs *second call after* — only the second call's idempotency matters
    here. Tests (a)-(d) cover the "drops the right thing" assertions.
    """
    local_root = tmp_path / "local_worktree" / "seed" / "lib" / "backend"
    local_root.mkdir(parents=True)
    foreign_lib = tmp_path / "other_worktree" / "seed" / "lib" / "backend" / "noctusai_lib"
    foreign_lib.mkdir(parents=True)

    finder = _make_class_mapping_finder(str(foreign_lib))
    sys.meta_path.append(finder)

    purge_shadowing_editable_finders(local_root)
    meta_path_after_first = list(sys.meta_path)
    assert finder not in meta_path_after_first, (
        "first call must drop the shadowing finder we appended"
    )

    # Second call must not raise AND must not change `sys.meta_path`.
    purge_shadowing_editable_finders(local_root)
    assert list(sys.meta_path) == meta_path_after_first, (
        "idempotency violated: second call mutated sys.meta_path"
    )
