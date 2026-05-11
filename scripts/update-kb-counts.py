#!/usr/bin/env python3
"""
update-kb-counts.py — regenerate derived-fact blocks in KB docs from the codebase.

Replaces content between markers of the form:
    <!-- kb-counts:start:<region> -->
    ...auto-updated content...
    <!-- kb-counts:end:<region> -->

Regions implemented:
    - inventory              Product-level counts table (02-LANDSCAPE.md)
    - database               Schema + table count summary (02-LANDSCAPE.md)
    - mcp_tools              MCP tool count (06-AGENTS.md)
    - agent_context_tools    MCP tool count inline (AGENT-CONTEXT.md)

Design:
    - Idempotent: running twice produces no diff.
    - Safe: never touches text outside the markers.
    - Fast: ~500ms on this repo.

Usage:
    python scripts/update-kb-counts.py            # write updates
    python scripts/update-kb-counts.py --check    # exit 1 if any doc would change
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


# ────────────────────────────────────────────────────────────────
# Counters
# ────────────────────────────────────────────────────────────────

PRODUCTS = [
    ("Core",             "products/core"),
    ("ERP",              "products/erp-imobiliario"),
    ("PF",               "products/personal-finance"),
    ("Therapy",          "products/therapy-platform"),
    ("Seed",             "products/seed"),
    ("Daily Life",       "products/daily-life"),
    ("Mailing",          "products/mailing"),
    ("AdConnect",        "products/adconnect"),
    ("Dev Team",         "products/dev-team"),
    ("Media Scheduling", "products/media-scheduling"),
    ("YouTube Crawler",  "products/youtube-crawler"),
    ("Imobi Scheduling", "products/imobi-scheduling"),
]


def _count_files(pattern_dir: Path, glob: str, exclude_names: set[str] = frozenset({"__init__.py"})) -> int:
    if not pattern_dir.is_dir():
        return 0
    return sum(1 for p in pattern_dir.rglob(glob) if p.is_file() and p.name not in exclude_names)


def _count_test_fns(tests_dir: Path) -> int:
    if not tests_dir.is_dir():
        return 0
    pat = re.compile(r"^\s*def\s+test_", re.MULTILINE)
    total = 0
    for p in tests_dir.rglob("test_*.py"):
        try:
            total += len(pat.findall(p.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            pass
    return total


def product_stats(product_path: str) -> dict:
    base = REPO / product_path
    routers = _count_files(base / "backend" / "app" / "routers", "*.py")
    services = _count_files(base / "backend" / "app" / "services", "*.py")
    pages = _count_files(base / "frontend" / "src" / "pages", "*.tsx")
    hooks = (
        _count_files(base / "frontend" / "src" / "hooks", "*.ts")
        + _count_files(base / "frontend" / "src" / "hooks", "*.tsx")
    )
    test_files = _count_files(base / "backend" / "tests", "test_*.py")
    test_fns = _count_test_fns(base / "backend" / "tests")
    return {
        "routers": routers,
        "services": services,
        "pages": pages,
        "hooks": hooks,
        "test_files": test_files,
        "test_fns": test_fns,
    }


def count_mcp_tools() -> int:
    server = REPO / "mcp" / "noctusai" / "server.py"
    if not server.is_file():
        return 0
    return len(re.findall(r"^\s*_tool\(", server.read_text(encoding="utf-8"), re.MULTILINE))


def count_schema_tables() -> dict[str, int]:
    """Count tables per schema across all migrations."""
    counts: dict[str, int] = {}
    # schema-qualified form: "CREATE TABLE [IF NOT EXISTS] <schema>.<name>"
    pat_qualified = re.compile(
        r'^CREATE TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?:"([a-z_\-]+)"|([a-z_]+))\.',
        re.IGNORECASE | re.MULTILINE,
    )
    # bare form in core migrations (implicitly public)
    pat_bare = re.compile(
        r'^CREATE TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?!"?[a-z_\-]+"?\s*\.)([a-z_]+)\s*\(',
        re.IGNORECASE | re.MULTILINE,
    )
    for mig_dir in (REPO / "products").glob("*/backend/migrations/*.sql"):
        try:
            text = mig_dir.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in pat_qualified.finditer(text):
            sch = m.group(1) or m.group(2)
            counts[sch] = counts.get(sch, 0) + 1
        if "/core/" in str(mig_dir):
            for _ in pat_bare.finditer(text):
                counts["public"] = counts.get("public", 0) + 1
    return counts


# ────────────────────────────────────────────────────────────────
# Region renderers
# ────────────────────────────────────────────────────────────────

def render_inventory() -> str:
    rows = [
        "| Product | Routers | Services | Pages | Hooks | Test files | Test fns |",
        "|---------|---------|----------|-------|-------|-----------|---------|",
    ]
    totals = {"routers": 0, "services": 0, "pages": 0, "hooks": 0, "test_files": 0, "test_fns": 0}
    for name, path in PRODUCTS:
        s = product_stats(path)
        rows.append(
            f"| {name} | {s['routers']} | {s['services']} | {s['pages']} | {s['hooks']} "
            f"| {s['test_files']} | {s['test_fns']:,} |"
        )
        for k in totals:
            totals[k] += s[k]
    rows.append(
        f"| **Total** | **{totals['routers']}** | **{totals['services']}** | **{totals['pages']}** "
        f"| **{totals['hooks']}** | **{totals['test_files']}** | **{totals['test_fns']:,}** |"
    )
    return "\n".join(rows) + "\n"


def render_database() -> str:
    counts = count_schema_tables()
    total = sum(counts.values())
    ordered = [
        "public", "erp", "personal-finance", "therapy", "daily_life", "mailing", "seed",
        "adconnect", "dev_team", "media_scheduling", "youtube_crawler", "imobi_scheduling",
    ]
    schemas_line = " + ".join(f"`{s}`" for s in ordered if s in counts)
    return (
        f"- **Schemas ({len([s for s in ordered if s in counts])}):** {schemas_line}.\n"
        f"- **Tables: {total}** distributed across the schemas.\n"
    )


def render_mcp_tools() -> str:
    n = count_mcp_tools()
    return f"**{n} tools total** (auto-counted from `mcp/noctusai/server.py`).\n"


def render_agent_context_tools() -> str:
    n = count_mcp_tools()
    return f"{n} tools\n"


REGIONS: dict[str, tuple[Path, callable]] = {
    "inventory": (REPO / "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md", render_inventory),
    "database": (REPO / "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md", render_database),
    "mcp_tools": (REPO / "KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md", render_mcp_tools),
    "agent_context_tools": (REPO / "KNOWLEDGE-BASE/AGENT-CONTEXT.md", render_agent_context_tools),
}


# ────────────────────────────────────────────────────────────────
# Replacement
# ────────────────────────────────────────────────────────────────

def replace_region(text: str, region: str, new_body: str) -> str:
    open_marker = f"<!-- kb-counts:start:{region} -->"
    close_marker = f"<!-- kb-counts:end:{region} -->"
    pat = re.compile(
        re.escape(open_marker) + r"(.*?)" + re.escape(close_marker),
        re.DOTALL,
    )
    body = new_body.rstrip("\n")
    return pat.sub(open_marker + "\n" + body + "\n" + close_marker, text)


def process_file(path: Path, regions_for_path: dict[str, callable], check_only: bool) -> bool:
    """Return True if file would change (check_only) or did change."""
    if not path.is_file():
        return False
    original = path.read_text(encoding="utf-8")
    updated = original
    for region, renderer in regions_for_path.items():
        updated = replace_region(updated, region, renderer())
    if updated == original:
        return False
    if not check_only:
        path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Exit 1 if any doc would change")
    args = parser.parse_args()

    # Group regions by file
    by_file: dict[Path, dict[str, callable]] = {}
    for name, (path, renderer) in REGIONS.items():
        by_file.setdefault(path, {})[name] = renderer

    any_changed = False
    for path, regions in by_file.items():
        changed = process_file(path, regions, check_only=args.check)
        if changed:
            any_changed = True
            verb = "would update" if args.check else "updated"
            print(f"  {verb}: {path.relative_to(REPO)} ({', '.join(regions)})")

    if args.check:
        if any_changed:
            print("KB counts drift detected. Run: python scripts/update-kb-counts.py", file=sys.stderr)
            return 1
        print("KB counts are up to date.")
        return 0

    if not any_changed:
        print("KB counts already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
