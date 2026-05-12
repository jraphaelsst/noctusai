"""Conftest helpers for parallel-worktree-safe testing.

When the host venv carries an editable-install of ``noctusai_lib`` (or
``noctusai_seed``) pointing at a sibling worktree, that finder shadows the
local ``sys.path`` entry and tests run against the wrong source tree. This
module ships the canonical shadow-purge helper used by seed-lib + every
product conftest.

Lift history (`projects/seed-shadow-purge-helper-lift/PROJECT.md`):
    * 4 verbatim-ish copies pre-existed (seed/lib + 3 products);
    * 3 carried a bug (inspect class-level ``MAPPING``); 1 (PF) carried the
      correct module-level fallback;
    * unified canonical lives here, supports both shapes defensively.

Generalization (2026-05-11, Engineer SP):
    * Engineer W (XML-FEEDS-VERIFY) surfaced the same shape for the
      ``noctusai_seed`` package — sibling-worktree editable installs can
      shadow ``noctusai_seed`` exactly as they shadow ``noctusai_lib``.
    * The package set is now a parameter (``package_names``) with the
      default ``("noctusai_lib", "noctusai_seed")`` so existing callers
      get both protections without touching their conftests.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

__all__ = ["purge_shadowing_editable_finders"]

_DEFAULT_PACKAGE_NAMES: tuple[str, ...] = ("noctusai_lib", "noctusai_seed")


def purge_shadowing_editable_finders(
    local_lib_root: Path,
    package_names: Iterable[str] = _DEFAULT_PACKAGE_NAMES,
) -> None:
    """Drop meta-path finders whose mapping for any of ``package_names`` points outside ``local_lib_root``.

    Handles BOTH shapes pip PEP-660 / hand-rolled finders use:

    * **class-level** ``MAPPING`` attribute (legacy / hypothetical);
    * **module-level** ``MAPPING`` dict on the finder's defining module —
      the actual real-world case for pip's
      ``__editable___<pkg>_<version>_finder.py`` shape, where
      ``sys.meta_path.append(_EditableFinder)`` registers the *class* but
      ``MAPPING`` lives on the module.

    Args:
        local_lib_root: the worktree's ``seed/lib/backend`` Path. Finders
            whose mapping for any package in ``package_names`` resolves
            *outside* this root are dropped from ``sys.meta_path``.
        package_names: iterable of package names to guard. Defaults to
            ``("noctusai_lib", "noctusai_seed")`` — both seed-side
            packages can be shadowed by sibling-worktree editable
            installs and need the same defense. Pass a narrower or wider
            tuple if a consumer needs custom coverage.

    Side-effects (by design — meant for conftest top-level use):

    * mutates ``sys.meta_path`` (drops shadowing finders);
    * drops cached entries for every guarded package from ``sys.modules``
      so they re-resolve through the local source tree on next import.

    Idempotent: calling twice in one process is safe (second call is a
    no-op when shadowing was already cleared).

    A finder whose ``__module__`` resolves to a module without ``MAPPING``
    is preserved (same effect as ``getattr`` returning ``None``) — the
    contract is "drop shadowing finders", not "drop unrecognized finders".

    Drop semantics with multiple packages: if a finder's mapping mentions
    ANY guarded package and ANY of those entries resolves outside
    ``local_lib_root``, the finder is dropped. This is the safe choice —
    a single editable finder typically maps one package, so the multi-
    package check is effectively an OR across independent finders.
    """
    local_target = str(local_lib_root.resolve())
    package_tuple = tuple(package_names)
    keep: list = []
    for finder in sys.meta_path:
        # Class-level MAPPING (legacy / hypothetical):
        mapping = getattr(finder, "MAPPING", None)
        if mapping is None:
            # Module-level MAPPING (pip's __editable___pkg_finder.py shape):
            mod_name = getattr(finder, "__module__", None)
            mod = sys.modules.get(mod_name) if mod_name else None
            mapping = getattr(mod, "MAPPING", None)
        drop = False
        if isinstance(mapping, dict):
            for pkg in package_tuple:
                if pkg in mapping:
                    target = str(Path(mapping[pkg]).resolve())
                    if not target.startswith(local_target):
                        # Editable finder bound to a different worktree — drop it.
                        drop = True
                        break
        if drop:
            continue
        keep.append(finder)
    sys.meta_path[:] = keep
    # Also drop any already-imported entries for guarded packages so they
    # re-resolve through our local source tree on next import.
    for name in list(sys.modules):
        for pkg in package_tuple:
            if name == pkg or name.startswith(f"{pkg}."):
                del sys.modules[name]
                break
