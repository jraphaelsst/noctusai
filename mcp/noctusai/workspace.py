"""Workspace-aware path resolution for the MCP toolkit.

A "workspace" is a directory that hosts a NoctusAI project. There are two
kinds: ``primary`` (the noc monorepo itself) and ``template`` (a sibling
folder that consumes noc strictly read-only via symlinks). Both planted
the same marker file at their root: ``.noctusai-workspace``.

Workspace-local MCP tools (status, file_proposal, scaffold_product) call
``get_workspace_root()`` to resolve cwd to the right workspace. Noc-shared
tools (catalog, kb_sync, lgpd, three_way_sync, ai_*) call ``get_noctusai_home()``
to always reach noc's authoritative resources regardless of where the MCP
was invoked from. Per-workspace MCP state (proposals registry, scan caches,
status snapshots) lives under ``<workspace>/.noctusai-state/``.

Resolver behavior:

1. Walk up from cwd looking for ``.noctusai-workspace``.
2. If found, parse its key=value fields and return the marker dir.
3. If not found anywhere up to filesystem root, fall back to file-relative
   resolution from this module (``Path(__file__).resolve().parents[2]``)
   which lands at noc root for the in-repo install. Back-compat is
   automatic — pre-workspace-aware code still finds the same root.

See KNOWLEDGE-BASE/CONTEXT/PATTERNS/template-workspace.md for the full
design + bootstrap recipe + read-only rule.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

MARKER_FILENAME = ".noctusai-workspace"
WORKSPACE_STATE_DIRNAME = ".noctusai-state"


@dataclass(frozen=True)
class WorkspaceContext:
    """Resolved identity of a NoctusAI workspace.

    ``root`` is the workspace's own filesystem root (where the marker
    was found OR the file-relative fallback noc root). ``noctusai_home``
    is the canonical noc repo path — equal to ``root`` for primary
    workspaces, and pointing back to noc for template workspaces.
    """

    kind: str  # "primary" | "template"
    name: str
    root: Path
    noctusai_home: Path
    marker_present: bool = False
    extra: dict = field(default_factory=dict)


def _parse_marker(marker_path: Path) -> dict:
    """Parse the marker file's key=value fields. Comments (#) ignored."""
    fields: dict = {}
    try:
        for line in marker_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip()
    except OSError as exc:
        logger.debug("Workspace marker unreadable at %s: %s", marker_path, exc)
    return fields


def find_workspace_marker(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (default cwd) looking for the marker file.

    Returns the marker's containing directory, or ``None`` if not found
    by the filesystem root.
    """
    cur = (start or Path.cwd()).resolve()
    while True:
        candidate = cur / MARKER_FILENAME
        if candidate.is_file():
            return cur
        if cur.parent == cur:  # filesystem root
            return None
        cur = cur.parent


def _fallback_noc_root() -> Path:
    """File-relative noc root — used when no marker is found.

    This module lives at ``mcp/noctusai/workspace.py``, so ``parents[2]``
    is the noc repo root.
    """
    return Path(__file__).resolve().parents[2]


def get_workspace_context(start: Path | None = None) -> WorkspaceContext:
    """Resolve the current workspace's full context.

    Marker-driven when present; file-relative fallback otherwise.
    """
    marker_dir = find_workspace_marker(start)
    if marker_dir is None:
        # No marker anywhere — fall back to file-relative noc root,
        # treat as primary. Back-compat for anything that imports MCP
        # outside a workspace (CI, ad-hoc scripts, tests run in tmp dirs).
        noc = _fallback_noc_root()
        return WorkspaceContext(
            kind="primary",
            name=noc.name,
            root=noc,
            noctusai_home=noc,
            marker_present=False,
        )

    fields = _parse_marker(marker_dir / MARKER_FILENAME)
    kind = fields.get("workspace_kind", "primary")
    name = fields.get("workspace_name", marker_dir.name)
    home_str = fields.get("noctusai_home")
    if home_str:
        noctusai_home = Path(home_str).expanduser().resolve()
    elif kind == "primary":
        noctusai_home = marker_dir
    else:
        # Template marker without explicit home — defensive fallback.
        noctusai_home = _fallback_noc_root()

    return WorkspaceContext(
        kind=kind,
        name=name,
        root=marker_dir,
        noctusai_home=noctusai_home,
        marker_present=True,
        extra=fields,
    )


def get_workspace_root(start: Path | None = None) -> Path:
    """Resolve the current workspace's root path.

    Workspace-local MCP tools (status, file_proposal, scaffold_product)
    use this to find their workspace's ``projects/`` and ``products/``.
    """
    return get_workspace_context(start).root


def get_noctusai_home(start: Path | None = None) -> Path:
    """Resolve the canonical noc repo path.

    Noc-shared MCP tools (catalog, kb_sync, lgpd, three_way_sync, ai_*)
    use this to always reach noc's authoritative resources regardless of
    where the MCP was invoked from.
    """
    return get_workspace_context(start).noctusai_home


def get_workspace_state_dir(start: Path | None = None) -> Path:
    """Resolve the per-workspace MCP state directory.

    Created on demand at ``<workspace>/.noctusai-state/``. Used for
    proposals registries, scan caches, status snapshots — anything the
    MCP toolkit writes that is workspace-scoped, not noc-shared.
    """
    state_dir = get_workspace_root(start) / WORKSPACE_STATE_DIRNAME
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


@lru_cache(maxsize=1)
def get_default_workspace_context() -> WorkspaceContext:
    """Singleton context resolved against import-time cwd.

    Provided as a convenience for module-level constants like
    ``REPO_ROOT = get_workspace_root()`` — those resolve once at import
    time, which is the right behavior for MCP server lifecycle (server
    boots in a known cwd; tools imported once; constant valid throughout).

    For tools that need to re-resolve per call (rare), use
    ``get_workspace_context()`` directly.
    """
    return get_workspace_context()


__all__ = [
    "MARKER_FILENAME",
    "WORKSPACE_STATE_DIRNAME",
    "WorkspaceContext",
    "find_workspace_marker",
    "get_workspace_context",
    "get_workspace_root",
    "get_noctusai_home",
    "get_workspace_state_dir",
    "get_default_workspace_context",
]
