"""`noctus.dev.refresh_dependabot_coverage` — keep `.github/dependabot.yml`'s
per-product npm blocks in sync with the products actually on disk.

WHY (2026-08-13). `.github/dependabot.yml` is a hand-maintained per-product list —
the SAME drift class this KB doc already gates on two other surfaces
(`check_hardcoded_product_slug_set`'s frozen slug literals,
`check_product_lockfile_dep_sync`'s stale lockfile snapshots): a mirrored artifact
that silently stops tracking the real thing it mirrors, invisible until an incident
makes it visible. Here the incident was `igig` (live in prod since 2026-08-09),
`orbity` (live), and `products/seed` (in `deploy/fleet/build-scope.txt`) carrying
**zero** dependency-update coverage — no Dependabot alert, no PR, nothing, because
nobody was watching that directory. Fixed by hand in `a40814b9` (coverage 12/12 +
an 8-entry fleet-major `ignore:` guard on all 14 npm blocks); this module is the
DERIVE-IT mechanism so it never silently regresses to 9/12 again.

Two questions, one file, same "derive don't hand-maintain" answer as
`deploy/fleet/build-scope.txt` (see `build_scope.py`):

    which products/*/frontend dirs are on disk right now?  →  filesystem, not the
                                                                catalog (Dependabot
                                                                should watch an
                                                                inactive-but-on-disk
                                                                product too — the file
                                                                already did, for
                                                                adconnect/daily-life/
                                                                dev-team/personal-
                                                                finance/therapy-
                                                                platform BEFORE this
                                                                module existed).
    does every npm block on disk still resolve + carry the fleet-major guard?
                                                            →  parse the committed
                                                                file's npm blocks.

TARGETED REPAIR, NOT A REWRITE. `dependabot.yml` carries load-bearing hand-written
rationale comments (why product requirements.txt files are omitted from pip
scanning, why every npm block groups+caps PRs, why the `ignore:` guard exists at
all) that a from-scratch YAML-dump regeneration would either lose or reformat away.
This module never rewrites the file; it only (a) APPENDS a brand-new block for a
product with no npm block yet, and (b) APPENDS missing `ignore:` entries into an
existing block (or adds a whole `ignore:` section if none exists) — every existing
line, comment, and entry survives byte-for-byte. A re-run on an already-correct
file changes nothing (`status == "in-sync"`).

REPORT, NEVER AUTO-DELETE. A block whose `directory:` no longer resolves to a
`package.json` (a deleted/renamed product) is reported in `stale` but never
removed automatically — restoring the product vs. deleting the block is a human
call this tool refuses to make silently.

Depth: `KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

#: Relative to repo root — the single dependabot config for the whole platform.
DEPENDABOT_REL = Path(".github") / "dependabot.yml"

#: The fleet-wide major-version freeze guard (`.github/dependabot.yml`'s own
#: comment: "declared in THREE places that must move together"). ORDER matches
#: the shape already on disk (used only when rendering a brand-new block —
#: detection itself is order-independent, a `set` difference).
MAJOR_GUARD_DEPS: tuple[str, ...] = (
    "react-router-dom",
    "react-router",
    "react",
    "react-dom",
    "@types/react",
    "@types/react-dom",
    "typescript",
    "vite",
)

_BLOCK_START_RE = re.compile(r'^  - package-ecosystem: "([a-z-]+)"\s*$')
_DIRECTORY_RE = re.compile(r'^    directory: "([^"]+)"\s*$')
_PRODUCT_DIR_RE = re.compile(r'^/products/([a-z0-9][a-z0-9-]*)/frontend$')
_LABELS_KEY_RE = re.compile(r'^    labels:\s*$')
_IGNORE_KEY_RE = re.compile(r'^    ignore:\s*$')
_IGNORE_ENTRY_NAME_RE = re.compile(r'^\s*- dependency-name: "([^"]+)"\s*$')
_GH_ACTIONS_MARKER_RE = re.compile(r'^  # ── GitHub Actions')


@dataclass
class _Block:
    """One `updates:` list entry, as line-index ranges into the ORIGINAL file —
    never mutated in place; repairs are computed as (anchor-line, new-lines)
    insertions applied bottom-to-top so earlier anchors stay valid."""

    ecosystem: str
    start: int  # index of the `- package-ecosystem:` line
    end: int  # exclusive — index of the next block's start, or EOF
    directory: str | None = None
    ignore_names: set[str] = field(default_factory=set)
    ignore_key_line: int | None = None
    labels_key_line: int | None = None


def _parse_blocks(lines: list[str]) -> list[_Block]:
    """Every `updates:` list entry in `dependabot.yml`, in file order.

    Line-based, not `yaml.safe_load` — a full-YAML round-trip through PyYAML's
    dumper reformats/loses comments, and every comment in this file is load-
    bearing (see module docstring). The keeper side is free to `yaml.safe_load`
    (read-only, never rewrites); this parser exists so the GENERATOR can make a
    surgical edit and leave everything else byte-identical.
    """
    starts = [i for i, ln in enumerate(lines) if _BLOCK_START_RE.match(ln)]
    blocks: list[_Block] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        ecosystem = _BLOCK_START_RE.match(lines[start]).group(1)
        block = _Block(ecosystem=ecosystem, start=start, end=end)
        for i in range(start, end):
            if block.directory is None:
                m = _DIRECTORY_RE.match(lines[i])
                if m:
                    block.directory = m.group(1)
            if block.ignore_key_line is None and _IGNORE_KEY_RE.match(lines[i]):
                block.ignore_key_line = i
            if block.labels_key_line is None and _LABELS_KEY_RE.match(lines[i]):
                block.labels_key_line = i
            m2 = _IGNORE_ENTRY_NAME_RE.match(lines[i])
            if m2:
                block.ignore_names.add(m2.group(1))
        blocks.append(block)
    return blocks


def _npm_product_blocks(blocks: list[_Block]) -> dict[str, _Block]:
    """`{slug: block}` for every npm block whose `directory:` is exactly
    `/products/<slug>/frontend` — the shape a product's block MUST have to be
    recognized as "this product's coverage" by leg 1 of the keeper."""
    out: dict[str, _Block] = {}
    for b in blocks:
        if b.ecosystem != "npm" or not b.directory:
            continue
        m = _PRODUCT_DIR_RE.match(b.directory)
        if m:
            out[m.group(1)] = b
    return out


def _dependabot_npm_dirs(blocks: list[_Block]) -> list[tuple[_Block, str]]:
    """`(block, relative-fs-path)` for every npm block with a `directory:` —
    ALL of them, not just product-shaped ones (`/seed/lib/frontend` and
    `/seed/framework/frontend` are npm blocks too, and both legs 2 + 3 of the
    keeper apply to the whole npm-ecosystem set, per the 2026-08-13 incident:
    "an 8-entry major guard on all 14 npm blocks")."""
    out: list[tuple[_Block, str]] = []
    for b in blocks:
        if b.ecosystem == "npm" and b.directory:
            out.append((b, b.directory.lstrip("/")))
    return out


def _has_npm_manifest(root: Path, rel_dir: str) -> bool:
    return (root / rel_dir / "package.json").is_file()


def _on_disk_product_slugs(root: Path) -> set[str]:
    """Every `products/<slug>` with a `frontend/package.json` — filesystem
    fact, not a catalog query. Deliberately NOT scoped to
    `ativo=true AND deploy_scope='live'`: the file already tracked inactive-
    but-on-disk products (adconnect, daily-life, dev-team, personal-finance,
    therapy-platform) before this module existed — Dependabot should still
    flag a CVE in a product we're not actively deploying."""
    products = root / "products"
    if not products.exists():
        return set()
    return {
        d.name
        for d in products.iterdir()
        if d.is_dir() and not d.name.startswith(".") and _has_npm_manifest(root, f"products/{d.name}/frontend")
    }


def _render_ignore_entry(name: str) -> list[str]:
    return [
        f'      - dependency-name: "{name}"\n',
        '        update-types: ["version-update:semver-major"]\n',
    ]


def _render_missing_block(slug: str, stamp: str) -> list[str]:
    lines = [
        f"  # {slug} — added automatically by noctus.dev.refresh_dependabot_coverage\n",
        f"  # (missing npm block detected on {stamp}).\n",
        '  - package-ecosystem: "npm"\n',
        f'    directory: "/products/{slug}/frontend"\n',
        "    schedule:\n",
        '      interval: "weekly"\n',
        "    open-pull-requests-limit: 2\n",
        "    groups:\n",
        "      all:\n",
        "        patterns:\n",
        '          - "*"\n',
        "    # FLEET-WIDE MAJORS are coordinated migrations, not bumps — see the\n",
        "    # /seed/lib/frontend block for the full rationale.\n",
        "    ignore:\n",
    ]
    for name in MAJOR_GUARD_DEPS:
        lines.extend(_render_ignore_entry(name))
    lines += [
        "    labels:\n",
        '      - "dependencies"\n',
        '      - "javascript"\n',
        "\n",
    ]
    return lines


def sync_dependabot_coverage(root: Path | None = None, write: bool = True) -> dict:
    """Repair `.github/dependabot.yml` in place. Returns
    `{ok, status, path, changed, added, guard_fixed, stale}`; `status` is
    `written` | `in-sync` | `would-write` | `error`. `added` is the sorted list
    of newly-created product slugs; `guard_fixed` maps `directory -> [missing
    dep names that were/would be added]`; `stale` is the sorted list of
    directories a block points at that no longer have a `package.json` —
    reported, never removed (see module docstring).
    """
    root = root or REPO_ROOT
    path = root / DEPENDABOT_REL
    if not path.is_file():
        return {"ok": False, "status": "error", "error": f"{DEPENDABOT_REL} not found under {root}"}

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    blocks = _parse_blocks(lines)

    npm_by_slug = _npm_product_blocks(blocks)
    on_disk = _on_disk_product_slugs(root)
    missing = sorted(on_disk - set(npm_by_slug))

    stale = sorted(
        rel for block, rel in _dependabot_npm_dirs(blocks) if not _has_npm_manifest(root, rel)
    )

    npm_blocks = [b for b in blocks if b.ecosystem == "npm" and b.directory]
    guard_gaps: dict[str, list[str]] = {}
    for b in npm_blocks:
        gap = [n for n in MAJOR_GUARD_DEPS if n not in b.ignore_names]
        if gap:
            guard_gaps[b.directory] = gap

    changed = bool(missing or guard_gaps)

    if not changed:
        return {
            "ok": True, "status": "in-sync", "path": str(path), "changed": False,
            "added": [], "guard_fixed": {}, "stale": stale,
        }

    if not write:
        return {
            "ok": True, "status": "would-write", "path": str(path), "changed": True,
            "added": missing, "guard_fixed": guard_gaps, "stale": stale,
        }

    inserts: list[tuple[int, list[str]]] = []

    for b in npm_blocks:
        gap = guard_gaps.get(b.directory or "")
        if not gap:
            continue
        new_entries: list[str] = []
        for name in MAJOR_GUARD_DEPS:
            if name in gap:
                new_entries.extend(_render_ignore_entry(name))
        anchor = b.labels_key_line if b.labels_key_line is not None else b.end
        if b.ignore_key_line is not None:
            # Existing (partial) `ignore:` list — append the missing entries
            # right before the anchor; everything already present is untouched.
            inserts.append((anchor, new_entries))
        else:
            # No `ignore:` key at all — add the whole section (with the
            # standard rationale comment) right before the anchor.
            section = [
                "    # FLEET-WIDE MAJORS are coordinated migrations, not bumps — see the\n",
                "    # /seed/lib/frontend block for the full rationale.\n",
                "    ignore:\n",
            ] + new_entries
            inserts.append((anchor, section))

    if missing:
        gh_actions_idx = next(
            (i for i, ln in enumerate(lines) if _GH_ACTIONS_MARKER_RE.match(ln)), len(lines)
        )
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_block_lines: list[str] = []
        for slug in missing:
            new_block_lines.extend(_render_missing_block(slug, stamp))
        inserts.append((gh_actions_idx, new_block_lines))

    # Apply strictly bottom-to-top by ORIGINAL anchor index so an earlier
    # insertion's target index is never shifted by a later (higher-index) one.
    for anchor, new_lines in sorted(inserts, key=lambda t: t[0], reverse=True):
        lines[anchor:anchor] = new_lines

    path.write_text("".join(lines), encoding="utf-8")
    return {
        "ok": True, "status": "written", "path": str(path), "changed": True,
        "added": missing, "guard_fixed": guard_gaps, "stale": stale,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.refresh_dependabot_coverage",
        description=(
            "Repair .github/dependabot.yml so it carries an npm block for every "
            "products/<slug>/frontend with a package.json, and the 8-entry "
            "fleet-major `ignore:` guard on every npm block. Targeted repair, not "
            "a rewrite — preserves every existing comment/entry byte-for-byte; "
            "only ADDS a missing product's block and any missing guard entries. "
            "Idempotent (no-op on an already-correct file). Reports (never "
            "removes) stale blocks whose directory no longer has a package.json "
            "— that is a human call. write=False previews. Fixes the 2026-08-13 "
            "incident class (igig/orbity/products-seed had zero Dependabot "
            "coverage). KB § PATTERNS/devops/product-lockfile-and-slug-drift.md."
        ),
    )
    def _refresh_dependabot_coverage(write: bool = True) -> dict:
        return sync_dependabot_coverage(write=write)


__all__ = [
    "DEPENDABOT_REL",
    "MAJOR_GUARD_DEPS",
    "sync_dependabot_coverage",
    "register",
]
