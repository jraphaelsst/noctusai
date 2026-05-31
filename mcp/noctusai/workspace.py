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

See KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md for the full
design + bootstrap recipe + read-only rule.
"""

from __future__ import annotations

import logging
import os
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
    workspaces, and pointing back to noc for seed workspaces.
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

    **Worktree boundary detection** (codified 2026-05-26 after N=3 cross-tree
    drift recurrence): if the walk crosses a `.../.claude/worktrees/<slug>/`
    boundary, STOP at the worktree's own root — the worktree is its own
    working tree and references must resolve there, not at the PRIMARY
    checkout above it. The worktree shares the primary's marker via git's
    worktree mechanism but lives under its own root. Sibling: the
    `NOCTUSAI_HOME` env override in `get_workspace_context` (explicit lever).
    """
    cur = (start or Path.cwd()).resolve()
    while True:
        candidate = cur / MARKER_FILENAME
        if candidate.is_file():
            return cur
        # Worktree boundary: if our parent is `.claude/worktrees`, `cur`
        # IS the worktree root (its own working tree). Stop here so cli.py
        # / direct imports invoked from inside a worktree resolve to the
        # worktree, not the primary checkout above.
        if cur.parent.name == "worktrees" and cur.parent.parent.name == ".claude":
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


def _detect_worktree_root(start: Path) -> Path | None:
    """Return the git-worktree root if `start` lives inside a
    `.../<primary>/.claude/worktrees/<slug>/` tree, else None.

    Codified 2026-05-26 after N=3 cross-tree drift: the primary's
    ``.noctusai-workspace`` marker is committed, so worktrees inherit
    a marker that points ``noctusai_home`` BACK to the primary checkout.
    That breaks cli.py / direct-import verification (REPO_ROOT == PRIMARY
    even when running from the worktree). Detection-based override:
    when cwd is inside a worktree subtree, the worktree's own root IS
    the workspace root. Sibling lever: ``NOCTUSAI_HOME`` env var.
    """
    cur = start.resolve()
    while cur.parent != cur:
        if cur.parent.name == "worktrees" and cur.parent.parent.name == ".claude":
            return cur
        cur = cur.parent
    return None


def get_workspace_context(start: Path | None = None) -> WorkspaceContext:
    """Resolve the current workspace's full context.

    Resolution priority (codified 2026-05-26 after N=3 cross-tree drift):
      (1) ``NOCTUSAI_HOME`` env var — explicit lever; bypass marker walk.
      (2) Worktree boundary detection in ``find_workspace_marker`` —
          stops the walk at `.claude/worktrees/<slug>/` (the worktree's
          own root).
      (3) `.noctusai-workspace` marker walk — original behavior.
      (4) File-relative fallback (`mcp/noctusai/workspace.py` parents[2]).
    """
    # (1) NOCTUSAI_HOME env override — highest priority. Lets cli.py /
    # direct imports run from anywhere and resolve to an explicit home
    # (mirrors the PYTHONHOME / VIRTUAL_ENV / GIT_DIR family of overrides).
    env_home = os.environ.get("NOCTUSAI_HOME")
    if env_home:
        home = Path(env_home).expanduser().resolve()
        if home.is_dir():
            return WorkspaceContext(
                kind="primary",
                name=home.name,
                root=home,
                noctusai_home=home,
                marker_present=False,
                extra={"resolved_via": "NOCTUSAI_HOME"},
            )
        logger.warning(
            "NOCTUSAI_HOME=%s does not point to a directory — falling "
            "through to marker discovery", env_home,
        )
    # (2) Worktree-boundary auto-detect — if cwd is inside
    # `.../<primary>/.claude/worktrees/<slug>/`, that worktree's own root IS
    # the workspace root (overrides the committed marker's PRIMARY-pointing
    # noctusai_home). N=3 codification, 2026-05-26.
    cwd = (start or Path.cwd()).resolve()
    wt_root = _detect_worktree_root(cwd)
    if wt_root is not None:
        return WorkspaceContext(
            kind="primary",
            name=wt_root.name,
            root=wt_root,
            noctusai_home=wt_root,
            marker_present=(wt_root / MARKER_FILENAME).is_file(),
            extra={"resolved_via": "worktree-boundary"},
        )
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
    if kind == "primary":
        # The PRIMARY marker lives AT the noc repo root, so its OWN directory
        # is the authoritative home — NEVER the committed `noctusai_home=` line.
        # That line is the author's absolute machine path (`/Users/<name>/…`);
        # trusting it makes REPO_ROOT resolve to the author's laptop on every
        # other checkout (CI, a fresh clone, a teammate) → cache/path errors.
        # Invisible until CI actually ran (the toolkit job was billing-gated).
        # 2026-05-31 portability fix. KB § PATTERNS/architect/seed-workspace.md.
        noctusai_home = marker_dir
    elif home_str:
        # NON-primary (seed/sibling) workspace: the marker legitimately points
        # `noctusai_home` BACK to a separate noc checkout — honor it.
        noctusai_home = Path(home_str).expanduser().resolve()
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


def resolve_caller_root(worktree_path: str | Path | None = None) -> Path:
    """Resolve the filesystem root a write-tool should target for the CALLER.

    The MCP server is a single long-running stdio process: it boots with
    one fixed CWD (typically the noc main worktree) and ``os.getcwd()``
    inside any tool returns the SERVER's CWD, not the caller's. The MCP
    protocol does not transmit caller-CWD per-call. Therefore write tools
    that need to land their output in a caller-specific worktree MUST
    accept an explicit ``worktree_path`` argument; auto-detection from
    server-side state is fundamentally impossible.

    Args:
        worktree_path: Caller-supplied path. Engineers calling from inside
            a ``git worktree add`` pass their worktree root (e.g.
            ``/Users/.../.claude/worktrees/agent-abc/``). Architects calling
            from main noc pass ``None`` (or omit) — the helper resolves to
            the canonical noc home.

    Returns:
        The Path to use as the root for all filesystem writes. Equal to
        ``get_noctusai_home()`` when ``worktree_path is None``; otherwise
        the validated worktree root.

    Raises:
        ValueError: ``worktree_path`` is given but does not look like a
        git worktree root (must be a directory containing a ``.git`` entry
        AND a ``.noctusai-workspace`` marker). No silent fallback —
        misuse should surface loudly, not silently write to noc.

    Background:
        Filed by ``projects/mcp-worktree-path-resolution/`` (2026-05-10).
        Surfaced by ``imobi-scheduling-bot-creation`` Phase 0+1 close —
        ``noctus.dev.scaffold_product`` wrote 58+ files to the noc main
        worktree from inside Engineer E's isolated worktree because
        ``REPO_ROOT`` was bound at server startup.
    """
    if worktree_path is None:
        return get_noctusai_home()

    root = Path(worktree_path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(
            f"resolve_caller_root: worktree_path is not a directory: {root}. "
            "Pass the engineer's worktree root (e.g. "
            "'/Users/.../.claude/worktrees/agent-<hex>/') or omit to land "
            "in noc main."
        )

    git_entry = root / ".git"
    if not git_entry.exists():
        raise ValueError(
            f"resolve_caller_root: worktree_path missing .git entry: {root}. "
            "Expected a git worktree root (the .git is typically a file "
            "pointing to the gitdir of the worktree). Pass the worktree "
            "root, not a subdirectory or unrelated path."
        )

    marker = root / MARKER_FILENAME
    if not marker.is_file():
        raise ValueError(
            f"resolve_caller_root: worktree_path missing {MARKER_FILENAME} marker: {root}. "
            "Worktrees scaffolded via the canonical recipe ship the marker. "
            "If this is a genuine worktree without the marker, create one "
            "via bootstrap-seed-workspace.sh or copy the marker manually."
        )

    return root


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
    "resolve_caller_root",
]
