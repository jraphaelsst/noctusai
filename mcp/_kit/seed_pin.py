"""In-tree seed pin — resolve `noctusai_lib` from THIS worktree's seed.

## Why this exists (zero-context)

The repo installs `noctusai_lib` editable (`pip install -e seed/lib/backend`).
An editable install registers an `_EditableFinder` on `sys.meta_path`
that **hard-pins** `noctusai_lib` to whatever worktree `pip install -e`
last ran in. In a multi-agent setup that pinned path is frequently a
*different, now-stale* `.claude/worktrees/agent-*` tree — one predating
a post-absorption package (e.g. `noctusai_lib.integrations.meta`). Because
`sys.meta_path` finders are consulted **before** `sys.path`, a plain
`sys.path.insert(0, <in-tree seed>)` **cannot** override the stale pin:
imports silently resolve against the wrong tree and fail on freshly-added
symbols.

Two connectors independently hand-rolled the same fix (`mcp/google`'s
`conftest.py` + `server.py`; `mcp/meta`'s `tests/test_smoke.py`). N=2 →
the DRY recurrence rule → formalized here so vista and every future
connector inherits the pin by construction via `_kit.bootstrap` instead
of re-deriving a third copy.

## What `pin_in_tree_seed` does

1. Walk up from `start` to the worktree root (marker: a dir containing
   both `.git` **and** `seed/lib/backend`).
2. Evict from `sys.meta_path` any finder whose resolved `noctusai_lib`
   location is **outside** that root — by inspecting its editable mapping
   (`_mapping` / `MAPPING`), with an `_EditableFinder`-by-name fallback
   for finders that expose no readable mapping.
3. Purge cached `noctusai_lib*` / `noctusai_seed*` modules so a
   re-import re-resolves cleanly.
4. Prepend the in-tree `seed/lib/backend` to `sys.path` so the regular
   `PathFinder` resolves `noctusai_lib` against this tree.

Idempotent (re-calling with the same root is a cheap no-op once the
in-tree path is already `sys.path[0]` and no stray finders remain),
logs at DEBUG, returns the resolved `seed/lib/backend` path. No silent
except — the only swallowed lookups are best-effort attribute probes on
third-party finder objects, each justified inline.

This is **not** a monkeypatch: no function/class is replaced. It corrects
a mis-pointed package *locator* so code exercises the tree it lives in —
the "codebase is source of truth" rule applied to import resolution.

Ordering contract: `_kit.bootstrap` calls this **before** any
`noctusai_lib` import so the pin wins. A connector composing the kit
gets it for free and must not import `noctusai_lib` ahead of the kit.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger("connector-kit.seed_pin")

_WORKTREE_MARKERS = (".git", "seed/lib/backend")


def _find_worktree_root(start: Path) -> Path:
    """Walk up from `start` to the first dir containing BOTH a `.git`
    entry and `seed/lib/backend`. Falls back to the filesystem-anchored
    ancestor that still has `seed/lib/backend` if no `.git` is found
    (covers a worktree whose `.git` is a file, plus exported trees)."""
    start = start.resolve()
    candidates = [start, *start.parents]
    for candidate in candidates:
        has_git = (candidate / ".git").exists()
        has_seed = (candidate / "seed" / "lib" / "backend").is_dir()
        if has_git and has_seed:
            return candidate
    # Fallback: deepest ancestor that still ships the seed (no .git
    # readable — e.g. a detached export). Never silent: log it.
    for candidate in candidates:
        if (candidate / "seed" / "lib" / "backend").is_dir():
            logger.debug(
                "seed_pin: no .git marker found walking up from %s; "
                "falling back to seed-only root %s",
                start,
                candidate,
            )
            return candidate
    raise RuntimeError(
        f"seed_pin: could not locate a worktree root with seed/lib/backend "
        f"walking up from {start}"
    )


def _editable_mapping(finder: object) -> dict | None:
    """Return the editable-install path mapping of a meta-path finder,
    or None if it is not an editable finder / exposes no mapping.

    `_EditableFinder` stores `{package: path}` under `_mapping` (newer
    setuptools) or `MAPPING` (older). The attribute probe is wrapped
    because `finder` is an arbitrary third-party object; a missing attr
    legitimately means "not an editable finder", which is not an error."""
    for attr in ("_mapping", "MAPPING"):
        try:
            value = getattr(finder, attr, None)
        except Exception as exc:  # noqa: BLE001 — third-party attr probe
            logger.debug(
                "seed_pin: probing %s.%s raised %r; treating as no-mapping",
                type(finder).__name__,
                attr,
                exc,
            )
            value = None
        if isinstance(value, dict):
            return value
    return None


def _pinned_noctusai_path(mapping: dict) -> str | None:
    """Extract the `noctusai_lib` location from an editable mapping.
    Values are str (a path) or a 1-tuple/list of paths depending on the
    setuptools version."""
    pinned = mapping.get("noctusai_lib")
    if isinstance(pinned, str):
        return pinned
    if isinstance(pinned, (list, tuple)) and pinned:
        return str(pinned[0])
    return None


def _looks_like_noctus_editable_finder(finder: object) -> bool:
    """Name-based fallback: an editable-install finder that exposes no
    readable mapping. setuptools registers these as the *class object*
    `_EditableFinder` from an `__editable__.*` shim module."""
    module = getattr(finder, "__module__", "") or ""
    name = getattr(finder, "__name__", "") or ""
    return "__editable__" in module and name == "_EditableFinder"


def pin_in_tree_seed(start: Path) -> Path:
    """Pin `noctusai_lib` resolution to the seed in `start`'s worktree.

    `start` — any path inside the worktree (typically the caller's
    `Path(__file__)`). Returns the resolved `seed/lib/backend` directory.

    Idempotent: evicting already-absent finders is a no-op, the cached
    `sys.modules` purge only touches stale entries, and a repeated
    `sys.path` prepend is deduped to a single leading entry.
    """
    root = _find_worktree_root(Path(start))
    seed_backend = root / "seed" / "lib" / "backend"
    if not seed_backend.is_dir():
        raise RuntimeError(
            f"seed_pin: worktree root {root} has no seed/lib/backend "
            f"(expected {seed_backend})"
        )
    target = str(seed_backend)

    evicted = 0
    for finder in list(sys.meta_path):
        mapping = _editable_mapping(finder)
        if mapping is not None:
            pinned = _pinned_noctusai_path(mapping)
            # Keep finders that have nothing to say about noctusai_lib,
            # and the (rare, correct) finder already pointing in-tree.
            if pinned is None or target in str(pinned):
                continue
        elif not _looks_like_noctus_editable_finder(finder):
            continue
        # Either: an editable finder pinning noctusai_lib OUTSIDE this
        # tree, or a no-mapping noctus editable finder we can't introspect
        # (assume stale — the in-tree sys.path prepend below is the
        # authoritative resolver once it is gone).
        sys.meta_path.remove(finder)
        evicted += 1

    purged = 0
    for name in list(sys.modules):
        if (
            name == "noctusai_lib"
            or name.startswith("noctusai_lib.")
            or name == "noctusai_seed"
            or name.startswith("noctusai_seed.")
        ):
            del sys.modules[name]
            purged += 1

    # Prepend the in-tree seed; dedupe so repeated calls don't grow path.
    if sys.path and sys.path[0] == target:
        pass
    else:
        try:
            sys.path.remove(target)
        except ValueError:
            pass  # not present yet — expected on first call
        sys.path.insert(0, target)

    logger.debug(
        "seed_pin: pinned noctusai_lib to %s (root=%s, evicted=%d finders, "
        "purged=%d cached modules)",
        target,
        root,
        evicted,
        purged,
    )
    return seed_backend


__all__ = ["pin_in_tree_seed"]
