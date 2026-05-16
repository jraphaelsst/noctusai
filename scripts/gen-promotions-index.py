#!/usr/bin/env python3
"""
gen-promotions-index.py — derive a seed-workspace's PROMOTIONS.md from its
`.promotions/*.md` manifest directory (the single source of truth).

`PROMOTIONS.md` is a DERIVED artifact, never hand-maintained. A hand-kept
parallel index drifts: the social-wiring-absorption W0.2 audit found the
originating workspace's hand-written `PROMOTIONS.md` listed only 7 of 14
manifests. This generator closes that drift class by regenerating the index
from `.promotions/` deterministically.

Replaces content between markers of the form:
    <!-- promotions:start -->
    ...auto-derived table...
    <!-- promotions:end -->

If `PROMOTIONS.md` is missing or has no markers, the whole file is
(re)written from the canonical template (header + markers).

Design (mirrors scripts/update-kb-counts.py):
    - Idempotent: running twice produces no diff.
    - Safe: only touches content between the markers (or a fresh file).
    - Resilient: unparseable manifests are listed under a "Needs attention"
      section instead of silently dropped (no-silent-errors).

Usage:
    python scripts/gen-promotions-index.py --workspace <dir>   # write
    python scripts/gen-promotions-index.py --workspace <dir> --check
        # exit 1 if PROMOTIONS.md would change (drift) — pre-commit / CI

The canonical manifest parser is reused from the promotion MCP module
(mcp/noctusai/tools/noctus/dev/promotion.py) so the index and the
`noctus.dev.promote_from_seed_workspace` pipeline never diverge on what a
manifest means. `mcp/` is a symlinked surface in every seed workspace, so
this import resolves identically in noc and in a workspace.

See KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md § Promotion manifest.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

START_MARKER = "<!-- promotions:start -->"
END_MARKER = "<!-- promotions:end -->"
PROMOTIONS_DIRNAME = ".promotions"
PROMOTIONS_INDEX = "PROMOTIONS.md"
# Manifest authors drop a copy of this file (one per promotable capability);
# it is a template, never itself an index row.
MANIFEST_TEMPLATE_NAME = "MANIFEST-TEMPLATE.md"
# The generator is copied into a workspace's .promotions/ for self-contained
# pre-commit `--check`; it is not an index row either.
GENERATOR_COPY_NAME = "gen-index.py"

_SKIP_MANIFEST_NAMES = {MANIFEST_TEMPLATE_NAME}


def _load_parser():
    """Import the canonical manifest parser from the promotion MCP module.

    `mcp/` is a symlinked surface in every seed workspace, so resolving the
    parser relative to this script's noc root works in noc AND when the
    generator copy runs from inside a workspace whose `mcp/` symlink points
    back at noc.
    """
    here = Path(__file__).resolve()
    # noc layout: <noc>/scripts/gen-promotions-index.py
    # workspace copy: <ws>/.promotions/gen-index.py  → mcp/ is the symlink
    candidates = [
        here.parents[1] / "mcp" / "noctusai" / "tools" / "noctus" / "dev",
        here.parents[1] / "mcp" / "noctusai",
    ]
    for c in candidates:
        if c.is_dir():
            sys.path.insert(0, str(c))
    from promotion import parse_manifest  # type: ignore  # noqa: E402

    return parse_manifest


def _manifest_files(promotions_dir: Path) -> list[Path]:
    if not promotions_dir.is_dir():
        return []
    return sorted(
        p
        for p in promotions_dir.glob("*.md")
        if p.is_file() and p.name not in _SKIP_MANIFEST_NAMES
    )


def _readiness(seed_first_analysis: str, body: str) -> str:
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


def build_index(workspace_root: Path) -> str:
    """Build the full PROMOTIONS.md body (header + table between markers)."""
    parse_manifest = _load_parser()
    promotions_dir = workspace_root / PROMOTIONS_DIRNAME
    name = workspace_root.name

    pending: list[tuple[str, str, str]] = []
    promoted: list[tuple[str, str, str, str]] = []
    unparseable: list[tuple[str, str]] = []

    for mf in _manifest_files(promotions_dir):
        try:
            m = parse_manifest(mf)
        except (ValueError, Exception) as exc:  # noqa: BLE001 — surface, don't drop
            unparseable.append((mf.name, str(exc).splitlines()[0][:120]))
            continue
        readiness = _readiness(m.seed_first_analysis, m.body)
        if m.promoted_on == "not-yet":
            pending.append((m.slug, m.intended_noc_destination, readiness))
        else:
            promoted.append(
                (m.slug, m.intended_noc_destination, readiness, m.promoted_on)
            )

    lines: list[str] = []
    lines.append(START_MARKER)
    lines.append("")
    lines.append(
        f"_DERIVED — do not hand-edit. Regenerate with "
        f"`python scripts/gen-promotions-index.py --workspace .`. "
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
    lines.append(END_MARKER)

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
        f"`python scripts/gen-promotions-index.py --workspace .` (the workspace "
        f"pre-commit hook runs `--check` and refuses drift).\n"
        f"\n"
        f"See KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md § Promotion manifest.\n"
        f"\n"
    )
    return header + "\n".join(lines) + "\n"


def render(workspace_root: Path) -> str:
    """Return the desired full PROMOTIONS.md content.

    If an existing PROMOTIONS.md has the markers, only the marker region is
    swapped (header/prose outside markers is preserved). Otherwise the file
    is (re)written wholesale from the canonical template.
    """
    fresh = build_index(workspace_root)
    index_path = workspace_root / PROMOTIONS_INDEX
    if not index_path.is_file():
        return fresh
    existing = index_path.read_text(encoding="utf-8")
    if START_MARKER not in existing or END_MARKER not in existing:
        return fresh
    new_block = fresh[fresh.index(START_MARKER) : fresh.index(END_MARKER) + len(END_MARKER)]
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL
    )
    swapped = pattern.sub(lambda _m: new_block, existing, count=1)
    if not swapped.endswith("\n"):
        swapped += "\n"
    return swapped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        default=".",
        help="Seed-workspace root (dir containing .promotions/). Default: cwd.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if PROMOTIONS.md would change (drift). No write.",
    )
    args = parser.parse_args(argv)

    workspace_root = Path(args.workspace).resolve()
    promotions_dir = workspace_root / PROMOTIONS_DIRNAME
    if not promotions_dir.is_dir():
        print(
            f"[gen-promotions-index] no {PROMOTIONS_DIRNAME}/ at {workspace_root} "
            f"— not a seed workspace (or no manifests yet). Nothing to do.",
            file=sys.stderr,
        )
        return 0

    desired = render(workspace_root)
    index_path = workspace_root / PROMOTIONS_INDEX
    current = index_path.read_text(encoding="utf-8") if index_path.is_file() else ""

    if args.check:
        if desired != current:
            print(
                f"[gen-promotions-index] DRIFT: {PROMOTIONS_INDEX} is stale vs "
                f"{PROMOTIONS_DIRNAME}/. Regenerate with "
                f"`python scripts/gen-promotions-index.py --workspace "
                f"{args.workspace}` and stage it.",
                file=sys.stderr,
            )
            return 1
        return 0

    if desired != current:
        index_path.write_text(desired, encoding="utf-8")
        print(f"[gen-promotions-index] regenerated {index_path}")
    else:
        print(f"[gen-promotions-index] {PROMOTIONS_INDEX} already up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
