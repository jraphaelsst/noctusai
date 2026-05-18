"""`noctus.dev.promote_from_seed_workspace` + `noctus.dev.list_promotions` —
absorption pipeline from a seed workspace into noc.

A seed workspace stores per-addition metadata under
``<workspace>/.promotions/<slug>.md`` with frontmatter:

    ---
    slug: <addition-slug>
    origin: <workspace-relative-path>
    intended_noc_destination: <noc-relative-path>
    layer_rationale: |
      <why this destination>
    seed_first_analysis: |
      Q1 ... Q6 ...
    dependencies_on_other_additions: []
    promoted_on: not-yet
    ---

    <prose body>

The promotion tool reads an entry, validates origin + destination,
copies the addition (file or directory) into noc, and rewrites
`promoted_on` to today's ISO date. Idempotent on already-promoted
entries (skips with a warning).

Single-file and directory `origin` values both supported; lists of
multiple `origin` paths supported in BOTH the inline form
(``origin: [a, b]``) AND the YAML block-list form (``origin:`` then
newline-indented ``- a`` / ``- b`` children). The same applies to
`intended_noc_destination` (a multi-element block-list is joined with
``; `` for the single-string dataclass field; a one-element list
collapses to the bare path). Minimal-deps hand parser — no PyYAML.

See KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md § Promotion manifest.
"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from workspace import (
    get_noctusai_home,
    get_workspace_context,
    get_workspace_root,
    resolve_caller_root,
)

logger = logging.getLogger(__name__)

PROMOTIONS_DIRNAME = ".promotions"
PROMOTIONS_INDEX = "PROMOTIONS.md"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass
class PromotionManifest:
    """Parsed `.promotions/<slug>.md` entry."""

    slug: str
    origin: list[str]  # workspace-relative paths
    intended_noc_destination: str  # noc-relative path (file OR directory)
    layer_rationale: str
    seed_first_analysis: str
    dependencies: list[str] = field(default_factory=list)
    promoted_on: str = "not-yet"
    body: str = ""
    raw_path: Path | None = None


def _parse_list_field(raw: str) -> list[str]:
    """Parse a list-shaped frontmatter value.

    Accepts:  `[]`, `[a, b]`, `[a]`, single-item bare strings.
    Returns:  python list of strings.
    """
    raw = raw.strip()
    if not raw or raw == "[]":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1]
        return [item.strip().strip("\"'") for item in inner.split(",") if item.strip()]
    # Bare scalar — treat as single-item list.
    return [raw.strip().strip("\"'")]


def _parse_block_scalar(lines: list[str], start_idx: int, base_indent: int) -> tuple[str, int]:
    """Parse a YAML `|` block scalar starting at lines[start_idx].

    Returns (content, end_idx). Indentation-aware: continues collecting
    lines while their indent exceeds base_indent.
    """
    collected: list[str] = []
    i = start_idx
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            collected.append("")
            i += 1
            continue
        line_indent = len(line) - len(line.lstrip())
        if line_indent <= base_indent and line.strip():
            break
        collected.append(line[base_indent + 2:] if line_indent > base_indent else line)
        i += 1
    return "\n".join(collected).rstrip(), i
def _parse_block_list(lines, start_idx, base_indent):
    """Parse a YAML block-list (``- item`` children) starting at lines[start_idx].

    Triggered when a key has an empty inline value and the following
    line(s) are more-indented ``- `` entries. Returns (items, end_idx).
    Stops at the first non-empty line whose indent is <= base_indent
    OR whose stripped content does not start with ``- `` (mirrors the
    indentation discipline of ``_parse_block_scalar``).
    """
    items = []
    i = start_idx
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        line_indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if line_indent <= base_indent or not stripped.startswith("- "):
            break
        item = stripped[2:].strip().strip("\"'")
        if item:
            items.append(item)
        i += 1
    return items, i


def parse_manifest(path: Path) -> PromotionManifest:
    """Parse a `.promotions/<slug>.md` file into a PromotionManifest."""
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(
            f"Promotion manifest {path} missing YAML frontmatter "
            f"(expected `---` block at top)."
        )
    front, body = m.group(1), m.group(2)

    fields: dict[str, str | list[str]] = {}
    lines = front.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.rstrip()
        if value.strip() == "|":
            base_indent = len(line) - len(line.lstrip())
            content, i = _parse_block_scalar(lines, i + 1, base_indent)
            fields[key] = content
            continue
        if not value.strip():
            base_indent = len(line) - len(line.lstrip())
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if (
                j < len(lines)
                and (len(lines[j]) - len(lines[j].lstrip())) > base_indent
                and lines[j].strip().startswith("- ")
            ):
                items, i = _parse_block_list(lines, i + 1, base_indent)
                fields[key] = items
                continue
        # Inline scalar or list.
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            fields[key] = _parse_list_field(value)
        else:
            fields[key] = value
        i += 1

    # Required fields.
    for required in ("slug", "origin", "intended_noc_destination"):
        if required not in fields:
            raise ValueError(f"Promotion manifest {path} missing required field: {required}")

    origin_raw = fields["origin"]
    if isinstance(origin_raw, list):
        origin = origin_raw
    else:
        origin = _parse_list_field(str(origin_raw))

    deps_raw = fields.get("dependencies_on_other_additions", [])
    if isinstance(deps_raw, list):
        deps = deps_raw
    else:
        deps = _parse_list_field(str(deps_raw))

    # `intended_noc_destination` may now arrive as a block-list (one
    # destination per origin). The dataclass field is a single `str`
    # (the promote pipeline copies multi-origin additions as children
    # under one dest dir); a list is joined with `; ` so the value is
    # faithful + non-empty for the 3 consumers (index, list_promotions,
    # promote). A single-element list collapses to the bare path so the
    # promote pipeline keeps working unchanged for the common case.
    dest_raw = fields["intended_noc_destination"]
    if isinstance(dest_raw, list):
        dest_str = dest_raw[0] if len(dest_raw) == 1 else "; ".join(dest_raw)
    else:
        dest_str = str(dest_raw)

    return PromotionManifest(
        slug=str(fields["slug"]),
        origin=origin,
        intended_noc_destination=dest_str,
        layer_rationale=str(fields.get("layer_rationale", "")),
        seed_first_analysis=str(fields.get("seed_first_analysis", "")),
        dependencies=deps,
        promoted_on=str(fields.get("promoted_on", "not-yet")),
        body=body,
        raw_path=path,
    )


def _manifest_path(workspace_root: Path, slug: str) -> Path:
    return workspace_root / PROMOTIONS_DIRNAME / f"{slug}.md"


def _all_manifests(workspace_root: Path) -> list[Path]:
    promotions_dir = workspace_root / PROMOTIONS_DIRNAME
    if not promotions_dir.is_dir():
        return []
    return sorted(p for p in promotions_dir.glob("*.md") if p.is_file())


def list_promotions(
    workspace_root: Path | None = None,
    *,
    worktree_path: str | Path | None = None,
) -> dict:
    """List promotion manifests in the current workspace.

    Args:
        workspace_root: Explicit seed-workspace root (test seam). When
            set, wins over ``worktree_path``.
        worktree_path: **Caller-aware path resolution.** When set AND
            ``workspace_root`` is None, the seed-workspace lookup walks
            up from the caller's worktree root instead of the MCP
            server's startup CWD. Engineers calling from inside a
            ``git worktree add`` MUST pass their worktree root unless
            they're targeting the server-startup workspace. See
            ``resolve_caller_root``. Note: a promotion manifest is
            specifically a SEED-workspace artifact; if the worktree is
            itself a primary workspace, this listing will be empty
            (and ``promote_from_seed_workspace`` will refuse).

    Returns: {"workspace": str, "pending": [...], "promoted": [...]}.
    Items: {"slug", "origin", "destination", "promoted_on"}.

    Raises:
        ValueError: ``worktree_path`` is given but does not look like a
        valid worktree root (per ``resolve_caller_root`` contract).
    """
    if workspace_root is not None:
        ws_root = workspace_root
    elif worktree_path is not None:
        ws_root = get_workspace_root(resolve_caller_root(worktree_path))
    else:
        ws_root = get_workspace_root()
    pending: list[dict] = []
    promoted: list[dict] = []
    for manifest_path in _all_manifests(ws_root):
        try:
            m = parse_manifest(manifest_path)
        except ValueError as exc:
            logger.warning("Skipping unparseable manifest %s: %s", manifest_path, exc)
            continue
        item = {
            "slug": m.slug,
            "origin": m.origin,
            "destination": m.intended_noc_destination,
            "promoted_on": m.promoted_on,
        }
        if m.promoted_on == "not-yet":
            pending.append(item)
        else:
            promoted.append(item)
    return {"workspace": str(ws_root), "pending": pending, "promoted": promoted}


def _validate_workspace(workspace_root: Path) -> None:
    """Refuse to promote from a primary workspace (noc itself).

    Promotion only makes sense from a seed workspace (additions in
    template land in noc). Primary→primary is meaningless.
    """
    ctx = get_workspace_context(workspace_root)
    if ctx.kind != "seed":
        raise ValueError(
            f"Refusing to promote from a {ctx.kind!r} workspace. "
            f"Promotion only flows from a seed workspace → noc. "
            f"(Workspace at {ctx.root} has kind={ctx.kind!r}.)"
        )


def _resolve_destination(noc_home: Path, dest_rel: str) -> Path:
    """Resolve the noc-relative destination, refusing escapes outside noc."""
    dest_rel = dest_rel.lstrip("/")
    dest = (noc_home / dest_rel).resolve()
    # Refuse if the resolved destination escaped noc_home (e.g. via `..`).
    try:
        dest.relative_to(noc_home.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Destination {dest_rel!r} resolves outside noc_home ({noc_home}). Refusing."
        ) from exc
    return dest


def promote_from_seed_workspace(
    slug: str,
    dry_run: bool = False,
    force: bool = False,
    workspace_root: Path | None = None,
    noctusai_home: Path | None = None,
    *,
    worktree_path: str | Path | None = None,
) -> dict:
    """Promote a template addition into noc per its `.promotions/<slug>.md` entry.

    Steps:
      1. Locate manifest at `<workspace>/.promotions/<slug>.md`.
      2. Validate workspace kind == "seed" (refuse from primary).
      3. Validate every `origin` path exists in workspace.
      4. Resolve `intended_noc_destination` (refuse `..` escapes).
      5. Refuse if destination already exists (unless `force=True`).
      6. Copy addition(s) into noc.
      7. Rewrite manifest's `promoted_on` to today's ISO date.

    Args:
        slug: Promotion-manifest slug (the ``.promotions/<slug>.md`` entry).
        dry_run: Compute + return the plan without copying anything.
        force: Re-promote already-promoted entries, overwriting destination.
        workspace_root: Explicit seed-workspace root (test seam).
        noctusai_home: Explicit noc-home destination (test seam).
        worktree_path: **Caller-aware path resolution.** When set:
            ``workspace_root`` resolution walks up from the caller's
            worktree root (so promotion finds the seed workspace
            adjacent to the worktree), AND ``noctusai_home`` falls back
            to the caller's worktree itself when not explicitly seamed.
            Engineers calling from inside a ``git worktree add`` MUST
            pass their worktree root unless they're targeting the
            server-startup workspace. See ``resolve_caller_root``.

    3-tier priority: explicit ``workspace_root`` / ``noctusai_home``
    seams > ``worktree_path`` > module defaults.

    Returns: {"slug", "origin", "destination", "files_copied",
              "promoted_on", "dry_run"}.

    Raises:
        ValueError: ``worktree_path`` is given but does not look like a
        valid worktree root (per ``resolve_caller_root`` contract).
    """
    # Resolve caller's worktree root once; reused for whichever of
    # workspace_root / noctusai_home is not explicitly seamed.
    caller_root: Path | None = None
    if worktree_path is not None:
        caller_root = resolve_caller_root(worktree_path)

    if workspace_root is not None:
        ws_root = workspace_root
    elif caller_root is not None:
        ws_root = get_workspace_root(caller_root)
    else:
        ws_root = get_workspace_root()
    _validate_workspace(ws_root)

    if noctusai_home is not None:
        noc_home = noctusai_home
    elif caller_root is not None:
        # When called from a worktree of noc, noctusai_home is the
        # worktree itself (not the original noc main) — per the
        # resolve_caller_root contract.
        noc_home = caller_root
    else:
        noc_home = get_noctusai_home()

    manifest_path = _manifest_path(ws_root, slug)
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"No promotion manifest at {manifest_path}. "
            f"Create `.promotions/{slug}.md` with required frontmatter."
        )
    manifest = parse_manifest(manifest_path)

    if manifest.promoted_on != "not-yet" and not force:
        raise ValueError(
            f"Manifest {slug!r} already promoted on {manifest.promoted_on}. "
            f"Use force=True to re-promote (overwrites destination)."
        )

    # Validate every origin exists.
    origin_paths: list[Path] = []
    for origin_rel in manifest.origin:
        origin_path = (ws_root / origin_rel.lstrip("/")).resolve()
        try:
            origin_path.relative_to(ws_root.resolve())
        except ValueError as exc:
            raise ValueError(
                f"origin {origin_rel!r} resolves outside workspace ({ws_root}). Refusing."
            ) from exc
        if not origin_path.exists():
            raise FileNotFoundError(
                f"origin {origin_rel!r} declared in manifest does not exist at {origin_path}."
            )
        origin_paths.append(origin_path)

    dest = _resolve_destination(noc_home, manifest.intended_noc_destination)

    # Refuse if destination exists (unless force).
    if dest.exists() and not force:
        raise FileExistsError(
            f"Destination {dest} already exists in noc. "
            f"Use force=True to overwrite (destructive — verify first)."
        )

    files_copied: list[str] = []

    if dry_run:
        return {
            "slug": slug,
            "origin": [str(p.relative_to(ws_root)) for p in origin_paths],
            "destination": str(dest.relative_to(noc_home)),
            "files_copied": [],
            "promoted_on": "dry-run",
            "dry_run": True,
            "noc_home": str(noc_home),
        }

    if len(origin_paths) == 1:
        # Single origin → dest is the canonical landing path.
        # Dir-to-dir: copytree origin → dest (replace if exists+force).
        # File-to-file: copy file → dest.
        op = origin_paths[0]
        if op.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(op, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(op, dest)
        files_copied.append(str(dest.relative_to(noc_home)))
    else:
        # Multi-origin → dest is a directory; each origin copied as a child.
        dest.mkdir(parents=True, exist_ok=True)
        for op in origin_paths:
            target = dest / op.name
            if op.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(op, target)
            else:
                shutil.copy2(op, target)
            files_copied.append(str(target.relative_to(noc_home)))

    # Rewrite manifest's `promoted_on` field.
    today = date.today().isoformat()
    text = manifest_path.read_text(encoding="utf-8")
    new_text = re.sub(
        r"^promoted_on:\s*.*$",
        f"promoted_on: {today}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    manifest_path.write_text(new_text, encoding="utf-8")

    return {
        "slug": slug,
        "origin": [str(p.relative_to(ws_root)) for p in origin_paths],
        "destination": str(dest.relative_to(noc_home)),
        "files_copied": files_copied,
        "promoted_on": today,
        "dry_run": False,
        "noc_home": str(noc_home),
    }


# ---------------------------------------------------------------------------
# Derived PROMOTIONS.md index generator.
#
# Absorbed from the former ``scripts/gen-promotions-index.py`` (behaviour-
# preserving — byte-identical output). PROMOTIONS.md is a DERIVED artifact,
# never hand-maintained: a hand-kept parallel index drifts (the
# social-wiring-absorption W0.2 audit found a hand-written PROMOTIONS.md
# listing only 7 of 14 manifests). This generator regenerates the index
# from ``.promotions/*.md`` deterministically. It reuses ``parse_manifest``
# (above) so the index and the ``promote_from_seed_workspace`` pipeline
# never diverge on what a manifest means. Idempotent; only the marker
# region is swapped (header/prose preserved); unparseable manifests are
# surfaced under "Needs attention" rather than silently dropped.
# ---------------------------------------------------------------------------

_PROMO_START_MARKER = "<!-- promotions:start -->"
_PROMO_END_MARKER = "<!-- promotions:end -->"
# Manifest authors drop a copy of this file (one per promotable capability);
# it is a template, never itself an index row.
_PROMO_MANIFEST_TEMPLATE_NAME = "MANIFEST-TEMPLATE.md"
_PROMO_SKIP_MANIFEST_NAMES = {_PROMO_MANIFEST_TEMPLATE_NAME}


def _index_manifest_files(promotions_dir: Path) -> list[Path]:
    if not promotions_dir.is_dir():
        return []
    return sorted(
        p
        for p in promotions_dir.glob("*.md")
        if p.is_file() and p.name not in _PROMO_SKIP_MANIFEST_NAMES
    )


def _index_readiness(seed_first_analysis: str, body: str) -> str:
    """Best-effort readiness signal pulled from the manifest text.

    Looks for an explicit `readiness:`/`N=` marker; falls back to `—`.
    Non-fatal: readiness is advisory metadata, not a contract.
    """
    hay = f"{seed_first_analysis}\n{body}"
    m = re.search(r"readiness[:\s]+([^\n]+)", hay, re.IGNORECASE)
    if m:
        return m.group(1).strip()[:40]
    m = re.search(r"\bN=\s*([0-9]+\+?)", hay)
    if m:
        return f"N={m.group(1)}"
    return "—"


def _index_build(workspace_root: Path) -> str:
    """Build the full PROMOTIONS.md body (header + table between markers)."""
    promotions_dir = workspace_root / PROMOTIONS_DIRNAME
    name = workspace_root.name

    pending: list[tuple[str, str, str]] = []
    promoted: list[tuple[str, str, str, str]] = []
    unparseable: list[tuple[str, str]] = []

    for mf in _index_manifest_files(promotions_dir):
        try:
            m = parse_manifest(mf)
        except (ValueError, Exception) as exc:  # noqa: BLE001 — surface, don't drop
            unparseable.append((mf.name, str(exc).splitlines()[0][:120]))
            continue
        readiness = _index_readiness(m.seed_first_analysis, m.body)
        if m.promoted_on == "not-yet":
            pending.append((m.slug, m.intended_noc_destination, readiness))
        else:
            promoted.append(
                (m.slug, m.intended_noc_destination, readiness, m.promoted_on)
            )

    lines: list[str] = []
    lines.append(_PROMO_START_MARKER)
    lines.append("")
    lines.append(
        f"_DERIVED — do not hand-edit. Regenerate with "
        f"`python mcp/noctusai/cli.py --gen-promotions-index --workspace .`. "
        f"Source of truth: `{PROMOTIONS_DIRNAME}/*.md`._"
    )
    lines.append("")
    lines.append("## Pending")
    lines.append("")
    if pending:
        lines.append("| slug | destination | readiness |")
        lines.append("|---|---|---|")
        for slug, dest, rd in sorted(pending):
            lines.append(f"| `{slug}` | `{dest}` | {rd} |")
    else:
        lines.append("_(none)_")
    lines.append("")
    lines.append("## Promoted")
    lines.append("")
    if promoted:
        lines.append("| slug | destination | readiness | promoted_on |")
        lines.append("|---|---|---|---|")
        for slug, dest, rd, on in sorted(promoted):
            lines.append(f"| `{slug}` | `{dest}` | {rd} | {on} |")
    else:
        lines.append("_(none)_")
    lines.append("")
    if unparseable:
        lines.append("## Needs attention (unparseable manifests)")
        lines.append("")
        lines.append("| manifest | error |")
        lines.append("|---|---|")
        for fname, err in sorted(unparseable):
            lines.append(f"| `{PROMOTIONS_DIRNAME}/{fname}` | {err} |")
        lines.append("")
    lines.append(_PROMO_END_MARKER)

    header = (
        f"# Promotion Manifest Index — {name}\n"
        f"\n"
        f"Additions in this seed workspace that are candidates for promotion "
        f"into noc. **This file is auto-derived from `{PROMOTIONS_DIRNAME}/*.md`** "
        f"— the manifest directory is the single source of truth. Do not "
        f"hand-maintain this index; a hand-kept parallel index drifts.\n"
        f"\n"
        f"Promote an entry with "
        f"`noctus.dev.promote_from_seed_workspace`; regenerate this index with "
        f"`python mcp/noctusai/cli.py --gen-promotions-index --workspace .` (the workspace "
        f"pre-commit hook runs `--check` and refuses drift).\n"
        f"\n"
        f"See KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md § Promotion manifest.\n"
        f"\n"
    )
    return header + "\n".join(lines) + "\n"


def _index_render(workspace_root: Path) -> str:
    """Return the desired full PROMOTIONS.md content.

    If an existing PROMOTIONS.md has the markers, only the marker region is
    swapped (header/prose outside markers is preserved). Otherwise the file
    is (re)written wholesale from the canonical template.
    """
    fresh = _index_build(workspace_root)
    index_path = workspace_root / PROMOTIONS_INDEX
    if not index_path.is_file():
        return fresh
    existing = index_path.read_text(encoding="utf-8")
    if _PROMO_START_MARKER not in existing or _PROMO_END_MARKER not in existing:
        return fresh
    new_block = fresh[
        fresh.index(_PROMO_START_MARKER) : fresh.index(_PROMO_END_MARKER)
        + len(_PROMO_END_MARKER)
    ]
    pattern = re.compile(
        re.escape(_PROMO_START_MARKER) + r".*?" + re.escape(_PROMO_END_MARKER),
        re.DOTALL,
    )
    swapped = pattern.sub(lambda _m: new_block, existing, count=1)
    if not swapped.endswith("\n"):
        swapped += "\n"
    return swapped


def gen_promotions_index(
    repo_root: Path | None = None,
    *,
    workspace_root: Path | None = None,
    check: bool = False,
    worktree_path: str | Path | None = None,
) -> dict:
    """Regenerate a seed-workspace's ``PROMOTIONS.md`` from ``.promotions/*.md``.

    Behaviour-preserving absorption of ``scripts/gen-promotions-index.py``
    (byte-identical output). PROMOTIONS.md is a DERIVED artifact, never
    hand-maintained. Idempotent (regenerating twice → byte-identical;
    only the marker region is swapped, header/prose preserved); unparseable
    manifests are surfaced under "Needs attention" not silently dropped.

    Args:
        repo_root: alias for ``workspace_root`` (the seed-workspace dir
            containing ``.promotions/``); kept for signature parity with
            the sibling absorbed tools. ``workspace_root`` wins if both
            are given.
        workspace_root: explicit seed-workspace root (test seam).
        check: if True, do NOT write; report whether PROMOTIONS.md would
            change (``drift`` key in the result).
        worktree_path: **Caller-aware path resolution.** When set AND
            neither ``workspace_root`` nor ``repo_root`` is given, the
            workspace root resolves against the caller's worktree.

    Returns:
        ``{"workspace": str, "index_path": str, "changed": bool,
        "drift": bool, "check": bool, "is_seed_workspace": bool}``.
        ``is_seed_workspace`` is False (and nothing is written) when the
        target has no ``.promotions/`` directory — a no-op, not an error
        (mirrors the former script's stderr-note exit-0 behaviour).
    """
    if workspace_root is not None:
        ws_root = workspace_root
    elif repo_root is not None:
        ws_root = repo_root
    elif worktree_path is not None:
        ws_root = resolve_caller_root(worktree_path)
    else:
        ws_root = get_workspace_root()
    ws_root = Path(ws_root).resolve()

    promotions_dir = ws_root / PROMOTIONS_DIRNAME
    index_path = ws_root / PROMOTIONS_INDEX
    if not promotions_dir.is_dir():
        logger.info(
            "gen_promotions_index: no %s/ at %s — not a seed workspace "
            "(or no manifests yet). Nothing to do.",
            PROMOTIONS_DIRNAME, ws_root,
        )
        return {
            "workspace": str(ws_root),
            "index_path": str(index_path),
            "changed": False,
            "drift": False,
            "check": check,
            "is_seed_workspace": False,
        }

    desired = _index_render(ws_root)
    current = (
        index_path.read_text(encoding="utf-8") if index_path.is_file() else ""
    )
    drift = desired != current

    changed = False
    if not check and drift:
        index_path.write_text(desired, encoding="utf-8")
        changed = True

    return {
        "workspace": str(ws_root),
        "index_path": str(index_path),
        "changed": changed,
        "drift": drift,
        "check": check,
        "is_seed_workspace": True,
    }


__all__ = [
    "PromotionManifest",
    "parse_manifest",
    "promote_from_seed_workspace",
    "list_promotions",
    "gen_promotions_index",
]


def register(server) -> None:
    @server.tool(
        name="noctus.dev.promote_from_seed_workspace",
        description=(
            "Promote a seed-workspace addition into noc per its `.promotions/<slug>.md` "
            "manifest. Reads origin path(s) + intended_noc_destination + seed-first "
            "analysis from the manifest, validates origin exists + destination is safe, "
            "copies file or directory into noc, rewrites manifest's `promoted_on` to "
            "today. Refuses from primary workspaces. Use `dry_run=True` first to "
            "preview the plan. Pass `worktree_path` when called from inside a git "
            "worktree so the seed-workspace lookup AND the noc destination land in "
            "the worktree NOT the MCP server's startup workspace. See "
            "KB § PATTERNS/mcp-tool-conventions.md."
        ),
    )
    def _promote(
        slug: str,
        dry_run: bool = False,
        force: bool = False,
        worktree_path: str | None = None,
    ) -> dict:
        return promote_from_seed_workspace(
            slug=slug,
            dry_run=dry_run,
            force=force,
            worktree_path=worktree_path,
        )

    @server.tool(
        name="noctus.dev.list_promotions",
        description=(
            "List promotion manifests in the current workspace, split into pending "
            "(`promoted_on=not-yet`) vs promoted (with date). Reads `.promotions/*.md`. "
            "See KB § PATTERNS/seed-workspace.md. Pass `worktree_path` when called "
            "from inside a git worktree."
        ),
    )
    def _list_promotions(worktree_path: str | None = None) -> dict:
        return list_promotions(worktree_path=worktree_path)

    @server.tool(
        name="noctus.dev.gen_promotions_index",
        description=(
            "Regenerate a seed-workspace's derived PROMOTIONS.md from its "
            "`.promotions/*.md` manifests (the single source of truth — a "
            "hand-kept parallel index drifts). Idempotent; only the marker "
            "region is swapped (header/prose preserved); unparseable manifests "
            "are surfaced under 'Needs attention' not silently dropped. Pass "
            "check=True to detect drift without writing (pre-commit / CI gate). "
            "No `.promotions/` dir → no-op (is_seed_workspace=False), not an "
            "error. Pass worktree_path when called from inside a git worktree. "
            "See KB § PATTERNS/seed-workspace.md § Promotion manifest."
        ),
    )
    def _gen_promotions_index(
        check: bool = False,
        worktree_path: str | None = None,
    ) -> dict:
        return gen_promotions_index(
            check=check,
            worktree_path=worktree_path,
        )
