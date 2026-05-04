"""Conftest helpers for parallel-worktree-safe testing.

When the host venv carries an editable-install of ``noctusai_lib`` pointing
at a sibling worktree, that finder shadows the local ``sys.path`` entry and
tests run against the wrong source tree. This module ships the canonical
shadow-purge helper used by seed-lib + every product conftest.

Lift history (`projects/seed-shadow-purge-helper-lift/PROJECT.md`):
    * 4 verbatim-ish copies pre-existed (seed/lib + 3 products);
    * 3 carried a bug (inspect class-level ``MAPPING``); 1 (PF) carried the
      correct module-level fallback;
    * unified canonical lives here, supports both shapes defensively.
"""
from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["purge_shadowing_editable_finders"]


def purge_shadowing_editable_finders(local_lib_root: Path) -> None:
    """Drop meta-path finders whose ``noctusai_lib`` mapping points outside ``local_lib_root``.

    Handles BOTH shapes pip PEP-660 / hand-rolled finders use:

    * **class-level** ``MAPPING`` attribute (legacy / hypothetical);
    * **module-level** ``MAPPING`` dict on the finder's defining module —
      the actual real-world case for pip's
      ``__editable___<pkg>_<version>_finder.py`` shape, where
      ``sys.meta_path.append(_EditableFinder)`` registers the *class* but
      ``MAPPING`` lives on the module.

    Args:
        local_lib_root: the worktree's ``seed/lib/backend`` Path. Finders
            whose ``noctusai_lib`` mapping resolves *outside* this root are
            dropped from ``sys.meta_path``.

    Side-effects (by design — meant for conftest top-level use):

    * mutates ``sys.meta_path`` (drops shadowing finders);
    * drops cached ``noctusai_lib*`` entries from ``sys.modules`` so they
      re-resolve through the local source tree on next import.

    Idempotent: calling twice in one process is safe (second call is a
    no-op when shadowing was already cleared).

    A finder whose ``__module__`` resolves to a module without ``MAPPING``
    is preserved (same effect as ``getattr`` returning ``None``) — the
    contract is "drop shadowing finders", not "drop unrecognized finders".
    """
    local_target = str(local_lib_root.resolve())
    keep: list = []
    for finder in sys.meta_path:
        # Class-level MAPPING (legacy / hypothetical):
        mapping = getattr(finder, "MAPPING", None)
        if mapping is None:
            # Module-level MAPPING (pip's __editable___pkg_finder.py shape):
            mod_name = getattr(finder, "__module__", None)
            mod = sys.modules.get(mod_name) if mod_name else None
            mapping = getattr(mod, "MAPPING", None)
        if isinstance(mapping, dict) and "noctusai_lib" in mapping:
            target = str(Path(mapping["noctusai_lib"]).resolve())
            if not target.startswith(local_target):
                # Editable finder bound to a different worktree — drop it.
                continue
        keep.append(finder)
    sys.meta_path[:] = keep
    # Also drop any already-imported `noctusai_lib*` modules so they
    # re-resolve through our local source tree on next import.
    for name in list(sys.modules):
        if name == "noctusai_lib" or name.startswith("noctusai_lib."):
            del sys.modules[name]
