"""noctus.dev.component_list — list seed organs with derived validation status.

Walks all ``kind=component`` nodes in the noc-graph cache, derives their
validation status from observable signals, and returns a sorted + filterable
list.  The canonical discoverability surface for the organ catalog.

Usage (MCP):
    noctus.dev.component_list sort="consumers_desc"
    noctus.dev.component_list sort="name" filter_status=["shelfware"]
    noctus.dev.component_list filter_status=["validated", "emerging"]

Usage (CLI):
    python mcp/noctusai/cli.py --component-list
    python mcp/noctusai/cli.py --component-list --sort name
    python mcp/noctusai/cli.py --component-list --filter-status shelfware

Validation status semantics
----------------------------
``validated``  — ≥3 consumers + has_test + CI green + no debt markers + no
                 recent bug-fixes. Proven, stable, ready for reuse.
``emerging``   — in use but one or more validation gates are open.
``shelfware``  — zero consumers. Built but not wired. Surface explicitly to
                 prevent the silent "available" anti-pattern.
``unknown``    — graph data missing; treat as ``emerging`` for reuse purposes.

Performance
-----------
Re-computes on every call (the graph is already in-process after the first
query).  Results are cache-keyed by ``aggregate_source_sha``; a sha match
returns the cached list without re-deriving.  The cache key is invalidated
whenever any graph source file changes.

KB § PATTERNS/architect/component-list-and-validation.md.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from settings import REPO_ROOT  # path constant — never compute via __file__

# Worktree-safe import of noctusai_lib.components.
#
# The editable install MetaPathFinder points at the PRIMARY git checkout, so
# a new ``noctusai_lib.components`` package added in a worktree is invisible
# by default.  We resolve the package at load time via the worktree's seed lib
# path (same strategy as mcp/noctusai/tests/conftest.py) so both the CLI and
# the MCP server can load the module from the correct tree.
def _ensure_components_importable() -> None:
    """Force-register noctusai_lib.components from the nearest seed lib."""
    import importlib.util as _ilu
    import sys

    if "noctusai_lib.components" in sys.modules:
        return  # already loaded

    # Candidate: the worktree's seed lib (this file is MCP; climb to repo root).
    this_file = Path(__file__).resolve()
    # Path: mcp/noctusai/tools/noctus/dev/component_list.py → 5 levels up = repo root
    repo_root_candidate = this_file.parents[5]
    seed_lib_candidate = repo_root_candidate / "seed" / "lib" / "backend"
    components_dir = seed_lib_candidate / "noctusai_lib" / "components"

    if not components_dir.exists():
        # Fall through — the regular editable install path may work in the
        # primary checkout after the branch is merged.
        return

    vs_path = components_dir / "validation_signal.py"
    init_path = components_dir / "__init__.py"

    if vs_path.exists() and "noctusai_lib.components.validation_signal" not in sys.modules:
        _vs_spec = _ilu.spec_from_file_location(
            "noctusai_lib.components.validation_signal",
            str(vs_path),
        )
        if _vs_spec and _vs_spec.loader:
            _vs_mod = _ilu.module_from_spec(_vs_spec)
            sys.modules["noctusai_lib.components.validation_signal"] = _vs_mod
            _vs_spec.loader.exec_module(_vs_mod)

    if init_path.exists():
        _pkg_spec = _ilu.spec_from_file_location(
            "noctusai_lib.components",
            str(init_path),
            submodule_search_locations=[str(components_dir)],
        )
        if _pkg_spec and _pkg_spec.loader:
            _pkg_mod = _ilu.module_from_spec(_pkg_spec)
            sys.modules["noctusai_lib.components"] = _pkg_mod
            _pkg_spec.loader.exec_module(_pkg_mod)


_ensure_components_importable()

# Module-level import so tests can patch ``tools.noctus.dev.component_list.compute_signal_inputs``.
from noctusai_lib.components.validation_signal import (  # noqa: E402
    compute_signal_inputs,
    derive_validation_status,
)

logger = logging.getLogger(__name__)

# ── Result model ──────────────────────────────────────────────────────────────


class ComponentListEntry(BaseModel):
    """One row in the component list."""

    name: str = Field(description="Component label (e.g. 'LoginForm').")
    path: str | None = Field(None, description="Repo-relative source path.")
    consumers_count: int = Field(
        description=(
            "Number of wired consumers derived from 'consumes_component' edges "
            "(or 'imports' edges as W1 fallback)."
        ),
    )
    validation_status: Literal["validated", "emerging", "shelfware", "unknown"] = Field(
        description=(
            "Derived validation status. "
            "validated=all-5-gates-pass; emerging=in-use-but-gaps; "
            "shelfware=0-consumers; unknown=missing-data."
        ),
    )
    last_touched: str | None = Field(
        None,
        description=(
            "ISO-8601 timestamp of the last graph-source-file change for this "
            "component path (from noc_graph_files cache table). None if unknown."
        ),
    )


# ── In-process result cache (keyed by graph aggregate_source_sha) ─────────────

_RESULT_CACHE: dict[str, list[ComponentListEntry]] = {}


def _get_cached(sha: str) -> list[ComponentListEntry] | None:
    return _RESULT_CACHE.get(sha)


def _set_cached(sha: str, entries: list[ComponentListEntry]) -> None:
    _RESULT_CACHE[sha] = entries


# ── Graph helpers ─────────────────────────────────────────────────────────────


def _load_graph_index(repo_root: Path):
    """Load and index the noc-graph, triggering a lazy rebuild if stale."""
    from tools.noctus.graph._loader import load_index
    return load_index(repo_root)


def _get_source_sha(repo_root: Path) -> str:
    """Return the current aggregate source sha (for cache invalidation)."""
    try:
        from tools.noctus.dev.noc_graph_cache import compute_source_sha
        return compute_source_sha(repo_root)
    except Exception as exc:
        logger.warning("component_list: cannot compute source sha — %s", exc)
        return ""


def _last_touched_for_path(path: str, repo_root: Path) -> str | None:
    """Look up the cached_at timestamp from noc_graph_files for a node path."""
    try:
        from tools.noctus.dev.noc_graph_cache import cache_path as _cp
        from tools.noctus.dev.cache_backend import apply_locking_pragmas
        cache_p = _cp(repo_root)
        if not cache_p.exists():
            return None
        conn = sqlite3.connect(str(cache_p))
        conn.row_factory = sqlite3.Row
        # WAL + busy_timeout — uniform cache locking discipline (this reads the
        # noc-graph cache, written by another module). KB § PATTERNS/common/cache-locking-discipline.md.
        apply_locking_pragmas(conn)
        try:
            row = conn.execute(
                "SELECT cached_at FROM noc_graph_files WHERE path = ?", (path,)
            ).fetchone()
            return row["cached_at"] if row else None
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("component_list: _last_touched_for_path failed — %s", exc)
        return None


def _count_consumers_from_index(index, node_id: str, component_label: str) -> int:
    """Count consumers of a component via the graph index.

    Prefers ``consumes_component`` in-edges; falls back to ``imports``
    in-edges when W1 hasn't landed (warning logged once).
    """
    from noctusai_lib.graph.schema import EdgeKind

    # Inbound consumes_component edges (source = consumer, target = component).
    consumes_edges = [
        e for e in index.in_edges.get(node_id, [])
        if e.kind.value == "consumes_component"
    ]
    if consumes_edges:
        return len(consumes_edges)

    # W1 fallback — inbound imports edges.
    import_edges = [
        e for e in index.in_edges.get(node_id, [])
        if e.kind.value == "imports"
    ]
    if import_edges:
        logger.warning(
            "component_list: no 'consumes_component' edges for %s — "
            "falling back to 'imports' edges (count=%d). "
            "W1 (re-export attribution fix) may not have landed yet.",
            component_label, len(import_edges),
        )
        return len(import_edges)

    return 0


# ── Core listing function ─────────────────────────────────────────────────────


def list_components(
    *,
    sort: Literal["consumers_desc", "name", "last_touched"] = "consumers_desc",
    filter_status: list[str] | None = None,
    repo_root: Optional[Path] = None,
) -> list[ComponentListEntry]:
    """List all component nodes with derived validation status.

    Parameters
    ----------
    sort:
        Sort order. ``consumers_desc`` (default) puts the most-consumed
        organs first — ideal for "what should I reuse?" queries.
        ``name`` is alphabetical.
        ``last_touched`` is newest-first.
    filter_status:
        Optional list of status values to include. ``None`` returns all.
        Example: ``["shelfware"]`` to audit zero-consumer components.
    repo_root:
        Override repo root (mainly for testing).

    Returns
    -------
    list[ComponentListEntry], sorted + filtered as requested.
    """
    from noctusai_lib.graph.schema import NodeKind

    root = repo_root or REPO_ROOT

    # Cache check.
    sha = _get_source_sha(root)
    cached = _get_cached(sha) if sha else None
    if cached is not None:
        entries = cached
    else:
        # Build the index (triggers lazy rebuild if stale).
        try:
            index = _load_graph_index(root)
        except FileNotFoundError:
            logger.warning(
                "component_list: noc-graph cache missing — run noctus.graph.build first. "
                "Returning empty list."
            )
            return []

        component_nodes = [
            n for n in index.graph.nodes
            if n.kind == NodeKind.COMPONENT
        ]

        entries = []
        for node in component_nodes:
            consumers_count = _count_consumers_from_index(index, node.id, node.label)

            # Compute signal inputs — for the MCP tool we use the graph index
            # neighbors as the "heavy lifting" proxy.  _find_test_file and
            # _has_remediate_markers still read disk; _count_recent_bugfix_commits
            # shells to git.
            component_path: Path | None = None
            if node.path:
                abs_p = root / node.path
                if abs_p.exists():
                    component_path = abs_p

            if component_path is not None:
                # Full signal computation from disk + git.
                # Pass a synthetic graph_neighbors_result built from what we have.
                synthetic_neighbors = {
                    "edges": [
                        {"kind": e.kind.value, "source": e.source, "target": e.target}
                        for e in (index.in_edges.get(node.id, []) + index.out_edges.get(node.id, []))
                    ]
                }
                try:
                    inputs = compute_signal_inputs(component_path, synthetic_neighbors, root)
                    # Override consumers_count with the index-derived count (more reliable
                    # than the synthetic edge walk inside compute_signal_inputs).
                    inputs["consumers_count"] = consumers_count
                except Exception as exc:
                    logger.warning(
                        "component_list: compute_signal_inputs failed for %s — %s",
                        node.label, exc,
                    )
                    inputs = {
                        "consumers_count": consumers_count,
                        "has_test": False,
                        "test_passes_ci": None,
                        "has_noc_remediate_markers": False,
                        "recent_bugfix_commits_14d": 0,
                    }
            else:
                # Path not resolvable — minimal inputs (consumers from graph).
                inputs = {
                    "consumers_count": consumers_count,
                    "has_test": False,
                    "test_passes_ci": None,
                    "has_noc_remediate_markers": False,
                    "recent_bugfix_commits_14d": 0,
                }

            status = derive_validation_status(
                component_name=node.label,
                **inputs,
            )

            last_touched = _last_touched_for_path(node.path, root) if node.path else None

            entries.append(ComponentListEntry(
                name=node.label,
                path=node.path,
                consumers_count=consumers_count,
                validation_status=status,
                last_touched=last_touched,
            ))

        if sha:
            _set_cached(sha, entries)

    # ── Filter ────────────────────────────────────────────────────────────────
    if filter_status:
        entries = [e for e in entries if e.validation_status in filter_status]

    # ── Sort ──────────────────────────────────────────────────────────────────
    if sort == "consumers_desc":
        entries = sorted(entries, key=lambda e: e.consumers_count, reverse=True)
    elif sort == "name":
        entries = sorted(entries, key=lambda e: e.name.lower())
    elif sort == "last_touched":
        # None last_touched sorts to end (oldest).
        entries = sorted(
            entries,
            key=lambda e: e.last_touched or "1970-01-01T00:00:00+00:00",
            reverse=True,
        )

    return entries


# ── MCP registration ──────────────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.component_list",
        description=(
            "List all seed organs (reusable components) with derived validation tags. "
            "Sort by 'consumers_desc' (default), 'name', or 'last_touched'. "
            "Filter by status: 'validated' | 'emerging' | 'shelfware' | 'unknown'. "
            "Shelfware = zero-consumer organs — built but not wired anywhere. "
            "Consumers counted via 'consumes_component' edges (W1); falls back to "
            "'imports' edges with a warning. "
            "KB § PATTERNS/architect/component-list-and-validation.md."
        ),
    )
    def _component_list(
        sort: Literal["consumers_desc", "name", "last_touched"] = "consumers_desc",
        filter_status: Optional[list[str]] = None,
    ) -> list[dict]:
        entries = list_components(sort=sort, filter_status=filter_status)
        return [e.model_dump() for e in entries]


__all__ = [
    "ComponentListEntry",
    "list_components",
    "register",
]
