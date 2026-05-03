"""`noctusai_promote_from_template` + `noctusai_list_promotions` —
absorption pipeline from a template workspace into noc.

A template workspace stores per-addition metadata under
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
multiple `origin` paths supported by writing a YAML-ish list (the parser
strips brackets and splits on commas — minimal-deps).

See KNOWLEDGE-BASE/CONTEXT/PATTERNS/template-workspace.md § Promotion manifest.
"""
from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from workspace import get_noctusai_home, get_workspace_context, get_workspace_root

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

    return PromotionManifest(
        slug=str(fields["slug"]),
        origin=origin,
        intended_noc_destination=str(fields["intended_noc_destination"]),
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


def list_promotions(workspace_root: Path | None = None) -> dict:
    """List promotion manifests in the current workspace.

    Returns: {"workspace": str, "pending": [...], "promoted": [...]}.
    Items: {"slug", "origin", "destination", "promoted_on"}.
    """
    ws_root = workspace_root or get_workspace_root()
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

    Promotion only makes sense from a template workspace (additions in
    template land in noc). Primary→primary is meaningless.
    """
    ctx = get_workspace_context(workspace_root)
    if ctx.kind != "template":
        raise ValueError(
            f"Refusing to promote from a {ctx.kind!r} workspace. "
            f"Promotion only flows from template → noc. "
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


def promote_from_template(
    slug: str,
    dry_run: bool = False,
    force: bool = False,
    workspace_root: Path | None = None,
    noctusai_home: Path | None = None,
) -> dict:
    """Promote a template addition into noc per its `.promotions/<slug>.md` entry.

    Steps:
      1. Locate manifest at `<workspace>/.promotions/<slug>.md`.
      2. Validate workspace kind == "template" (refuse from primary).
      3. Validate every `origin` path exists in workspace.
      4. Resolve `intended_noc_destination` (refuse `..` escapes).
      5. Refuse if destination already exists (unless `force=True`).
      6. Copy addition(s) into noc.
      7. Rewrite manifest's `promoted_on` to today's ISO date.

    Returns: {"slug", "origin", "destination", "files_copied",
              "promoted_on", "dry_run"}.
    """
    ws_root = workspace_root or get_workspace_root()
    _validate_workspace(ws_root)
    noc_home = noctusai_home or get_noctusai_home()

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


__all__ = [
    "PromotionManifest",
    "parse_manifest",
    "promote_from_template",
    "list_promotions",
]
