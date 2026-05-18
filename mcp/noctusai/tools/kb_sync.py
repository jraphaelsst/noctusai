"""kb_sync tool — native KB-sync verification + KB-count regeneration.

Two native-Python ports (no subprocess shim):

  * ``verify_kb_sync()`` — native re-implementation of
    ``scripts/verify-kb-sync.sh``. Validates that every
    ``KNOWLEDGE-BASE/...md`` pointer in CLAUDE.md / CLAUDE/*.md resolves,
    that every top-level KB doc is indexed in INDEX.md, and that the
    INDEX.md Layout tree reflects the KB filesystem. Public name /
    signature / ``KBSyncResult`` return shape are PRESERVED byte-for-byte
    so ``cli.py --verify-kb-sync`` keeps working untouched (it reads
    ``stdout`` / ``stderr`` / ``exit_code``).

  * ``update_kb_counts(check=False)`` — native port of
    ``scripts/update-kb-counts.py``. Regenerates the
    ``<!-- kb-counts:start:X -->…<!-- kb-counts:end:X -->`` blocks for
    regions inventory / database / mcp_tools / agent_context_tools.
    ``check=True`` reports drift without writing (exit-1 semantics →
    ``drift`` flag in the returned dict).

Callable from:
  - CLI:   ``python mcp/noctusai/cli.py --verify-kb-sync``
  - MCP:   ``noctus.dev.kb_sync`` (registered below)
  - Code:  ``from tools.kb_sync import verify_kb_sync, update_kb_counts``

Exit-code parity with the retired ``verify-kb-sync.sh``:
  0 — synced
  1 — broken pointer in a CLAUDE.md / CLAUDE/*.md router
  2 — KB doc exists but is not referenced by INDEX.md, OR Layout-tree drift
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Callable, TypedDict

from settings import REPO_ROOT


# ════════════════════════════════════════════════════════════════════
# verify_kb_sync — native port of scripts/verify-kb-sync.sh
# ════════════════════════════════════════════════════════════════════

CLAUDE_MD = "CLAUDE.md"
KB_INDEX = "KNOWLEDGE-BASE/INDEX.md"
KB_DIR = "KNOWLEDGE-BASE"

# Subtrees indexed collectively — excluded from the "must be indexed" +
# "must be in Layout tree" checks (mirrors the .sh `case` arms).
_COLLECTIVE_SUBTREES = ("SKILLS", "WORKFLOWS", "MCP-SERVERS", "EVALS")

# `grep -hoE '`KNOWLEDGE-BASE/[^`]+\.md`'` then `sed 's/`//g'`
_POINTER_RE = re.compile(r"`(KNOWLEDGE-BASE/[^`]+\.md)`")

# INDEX.md Layout-tree token scan: `grep -oE '[A-Za-z0-9_-]+\.md'`
_MD_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+\.md")


class KBSyncResult(TypedDict):
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def _iter_kb_docs(root: Path) -> list[Path]:
    """`find KNOWLEDGE-BASE -type f -name '*.md' ! -path '*/.*' | sort -u`."""
    kb = root / KB_DIR
    if not kb.is_dir():
        return []
    out: list[Path] = []
    for p in kb.rglob("*.md"):
        if not p.is_file():
            continue
        # `! -path '*/.*'` — skip any path component starting with a dot.
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        out.append(p)
    return sorted(out, key=lambda p: str(p.relative_to(root)))


def _is_collective(rel_posix: str) -> bool:
    return any(
        rel_posix.startswith(f"{KB_DIR}/{sub}/") for sub in _COLLECTIVE_SUBTREES
    )


def _extract_layout_md_tokens(index_text: str) -> set[str]:
    """`sed -n '/^## Layout/,/^---/p' | grep -oE '[A-Za-z0-9_-]+\\.md'`.

    Captures lines from the first ``## Layout`` line through the next
    line that is exactly ``---`` (inclusive of both, as ``sed`` does).
    """
    tokens: set[str] = set()
    in_block = False
    for line in index_text.splitlines():
        if not in_block:
            if line.startswith("## Layout"):
                in_block = True
            else:
                continue
        # in_block == True (the `## Layout` line is included by sed)
        tokens.update(_MD_TOKEN_RE.findall(line))
        if line == "---":
            break
    return tokens


def verify_kb_sync() -> KBSyncResult:
    """Native KB-sync verifier. Behaviour-preserving vs verify-kb-sync.sh.

    Returns a structured result whose ``stdout`` / ``stderr`` /
    ``exit_code`` mirror the retired shell script exactly so the CLI
    consumer needs no change.
    """
    root = Path(REPO_ROOT)
    out = io.StringIO()
    err = io.StringIO()
    errors = 0
    warnings = 0

    # ─── 1. CLAUDE.md + topical CLAUDE/*.md pointers resolve ──────────
    out.write(
        "Checking CLAUDE.md + CLAUDE/*.md pointers resolve to real KB files...\n"
    )
    router_files = [root / CLAUDE_MD]
    claude_dir = root / "CLAUDE"
    if claude_dir.is_dir():
        # `find CLAUDE -maxdepth 2 -type f -name '*.md' | sort -u`
        nested: list[Path] = []
        for p in claude_dir.rglob("*.md"):
            if not p.is_file():
                continue
            depth = len(p.relative_to(claude_dir).parts)  # 1 == direct child
            if depth <= 2:
                nested.append(p)
        router_files.extend(sorted(nested, key=lambda p: str(p)))

    pointers: set[str] = set()
    for rf in router_files:
        try:
            text = rf.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in _POINTER_RE.finditer(text):
            pointers.add(m.group(1))

    for ptr in sorted(pointers):
        # Skip illustrative brace-alternation patterns (`{a,b}.md`).
        if "{" in ptr:
            continue
        if not (root / ptr).is_file():
            err.write(
                f"  ✗ BROKEN: {ptr} (referenced by a CLAUDE.md / "
                f"CLAUDE/*.md router, not on disk)\n"
            )
            errors += 1

    kb_docs = _iter_kb_docs(root)

    # ─── 2. Top-level KB docs are indexed in INDEX.md ────────────────
    out.write(f"Checking all KB docs are indexed in {KB_INDEX}...\n")
    index_path = root / KB_INDEX
    index_text = (
        index_path.read_text(encoding="utf-8", errors="ignore")
        if index_path.is_file()
        else ""
    )
    for doc in kb_docs:
        rel = doc.relative_to(root).as_posix()
        if rel == KB_INDEX:
            continue
        if rel == f"{KB_DIR}/AGENT-CONTEXT.md":
            continue
        if _is_collective(rel):
            continue
        base = doc.name
        if base not in index_text:
            err.write(f"  ⚠ NOT INDEXED: {rel}\n")
            warnings += 1

    # ─── 3. INDEX.md Layout tree reflects the filesystem ─────────────
    out.write(f"Checking {KB_INDEX} Layout tree reflects KB filesystem...\n")
    layout_tokens = _extract_layout_md_tokens(index_text)
    for doc in kb_docs:
        rel = doc.relative_to(root).as_posix()
        if rel == KB_INDEX:
            continue
        if _is_collective(rel):
            continue
        base = doc.name
        if base not in layout_tokens:
            err.write(
                f"  ⚠ NOT IN LAYOUT TREE: {rel} (visible in INDEX.md "
                f"tables but missing from the Layout sketch)\n"
            )
            warnings += 1

    # ─── 4. Summary ──────────────────────────────────────────────────
    out.write("\n")
    if errors == 0 and warnings == 0:
        out.write(
            "✓ KB sync OK — all CLAUDE.md pointers resolve, all KB "
            "docs indexed, Layout tree current.\n"
        )
        exit_code = 0
    elif errors > 0:
        err.write(
            f"✗ {errors} broken pointer(s) in CLAUDE.md. Fix before "
            f"commit.\n"
        )
        exit_code = 1
    else:
        err.write(
            f"⚠ {warnings} drift warning(s). Add to {KB_INDEX} "
            f"(Layout tree or topic tables as applicable).\n"
        )
        exit_code = 2

    return {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "stdout": out.getvalue(),
        "stderr": err.getvalue(),
    }


# ════════════════════════════════════════════════════════════════════
# update_kb_counts — native port of scripts/update-kb-counts.py
# ════════════════════════════════════════════════════════════════════

_PRODUCTS = [
    ("Core", "products/core"),
    ("ERP", "products/erp-imobiliario"),
    ("PF", "products/personal-finance"),
    ("Therapy", "products/therapy-platform"),
    ("Seed", "products/seed"),
    ("Daily Life", "products/daily-life"),
    ("AdConnect", "products/adconnect"),
    ("Dev Team", "products/dev-team"),
]


def _count_files(
    pattern_dir: Path, glob: str, exclude_names: frozenset[str] = frozenset({"__init__.py"})
) -> int:
    if not pattern_dir.is_dir():
        return 0
    return sum(
        1
        for p in pattern_dir.rglob(glob)
        if p.is_file() and p.name not in exclude_names
    )


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


def _product_stats(repo: Path, product_path: str) -> dict[str, int]:
    base = repo / product_path
    routers = _count_files(base / "backend" / "app" / "routers", "*.py")
    services = _count_files(base / "backend" / "app" / "services", "*.py")
    pages = _count_files(base / "frontend" / "src" / "pages", "*.tsx")
    hooks = _count_files(base / "frontend" / "src" / "hooks", "*.ts") + _count_files(
        base / "frontend" / "src" / "hooks", "*.tsx"
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


def _count_mcp_tools(repo: Path) -> int:
    server = repo / "mcp" / "noctusai" / "server.py"
    if not server.is_file():
        return 0
    return len(
        re.findall(
            r"^\s*_tool\(", server.read_text(encoding="utf-8"), re.MULTILINE
        )
    )


def _count_schema_tables(repo: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    pat_qualified = re.compile(
        r'^CREATE TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?:"([a-z_\-]+)"|([a-z_]+))\.',
        re.IGNORECASE | re.MULTILINE,
    )
    pat_bare = re.compile(
        r'^CREATE TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(?!"?[a-z_\-]+"?\s*\.)([a-z_]+)\s*\(',
        re.IGNORECASE | re.MULTILINE,
    )
    for mig in (repo / "products").glob("*/backend/migrations/*.sql"):
        try:
            text = mig.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in pat_qualified.finditer(text):
            sch = m.group(1) or m.group(2)
            counts[sch] = counts.get(sch, 0) + 1
        if "/core/" in str(mig):
            for _ in pat_bare.finditer(text):
                counts["public"] = counts.get("public", 0) + 1
    return counts


def _render_inventory(repo: Path) -> str:
    rows = [
        "| Product | Routers | Services | Pages | Hooks | Test files | Test fns |",
        "|---------|---------|----------|-------|-------|-----------|---------|",
    ]
    totals = {
        "routers": 0,
        "services": 0,
        "pages": 0,
        "hooks": 0,
        "test_files": 0,
        "test_fns": 0,
    }
    for name, path in _PRODUCTS:
        s = _product_stats(repo, path)
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


def _render_database(repo: Path) -> str:
    counts = _count_schema_tables(repo)
    total = sum(counts.values())
    ordered = [
        "public",
        "erp",
        "personal-finance",
        "therapy",
        "daily_life",
        "seed",
        "adconnect",
        "dev_team",
    ]
    schemas_line = " + ".join(f"`{s}`" for s in ordered if s in counts)
    return (
        f"- **Schemas ({len([s for s in ordered if s in counts])}):** {schemas_line}.\n"
        f"- **Tables: {total}** distributed across the schemas.\n"
    )


def _render_mcp_tools(repo: Path) -> str:
    n = _count_mcp_tools(repo)
    return f"**{n} tools total** (auto-counted from `mcp/noctusai/server.py`).\n"


def _render_agent_context_tools(repo: Path) -> str:
    n = _count_mcp_tools(repo)
    return f"{n} tools\n"


def _regions(repo: Path) -> dict[str, tuple[Path, Callable[[Path], str]]]:
    return {
        "inventory": (
            repo / "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md",
            _render_inventory,
        ),
        "database": (
            repo / "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md",
            _render_database,
        ),
        "mcp_tools": (
            repo / "KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md",
            _render_mcp_tools,
        ),
        "agent_context_tools": (
            repo / "KNOWLEDGE-BASE/AGENT-CONTEXT.md",
            _render_agent_context_tools,
        ),
    }


def _replace_region(text: str, region: str, new_body: str) -> str:
    open_marker = f"<!-- kb-counts:start:{region} -->"
    close_marker = f"<!-- kb-counts:end:{region} -->"
    pat = re.compile(
        re.escape(open_marker) + r"(.*?)" + re.escape(close_marker),
        re.DOTALL,
    )
    body = new_body.rstrip("\n")
    return pat.sub(open_marker + "\n" + body + "\n" + close_marker, text)


def _process_file(
    path: Path,
    regions_for_path: dict[str, Callable[[Path], str]],
    repo: Path,
    check_only: bool,
) -> bool:
    if not path.is_file():
        return False
    original = path.read_text(encoding="utf-8")
    updated = original
    for region, renderer in regions_for_path.items():
        updated = _replace_region(updated, region, renderer(repo))
    if updated == original:
        return False
    if not check_only:
        path.write_text(updated, encoding="utf-8")
    return True


def update_kb_counts(check: bool = False) -> dict[str, Any]:
    """Native port of scripts/update-kb-counts.py.

    Regenerates the ``kb-counts`` marker blocks. ``check=True`` reports
    drift without writing — ``drift`` mirrors the shell script's exit-1.

    Returns ``{ok, drift, changed, files, message}``.
    """
    repo = Path(REPO_ROOT)
    by_file: dict[Path, dict[str, Callable[[Path], str]]] = {}
    for name, (path, renderer) in _regions(repo).items():
        by_file.setdefault(path, {})[name] = renderer

    changed_files: list[str] = []
    any_changed = False
    for path, regions in by_file.items():
        changed = _process_file(path, regions, repo, check_only=check)
        if changed:
            any_changed = True
            try:
                rel = str(path.relative_to(repo))
            except ValueError:
                rel = str(path)
            changed_files.append(f"{rel} ({', '.join(regions)})")

    if check:
        if any_changed:
            msg = (
                "KB counts drift detected. Run: "
                "python mcp/noctusai/cli.py --update-kb-counts"
            )
        else:
            msg = "KB counts are up to date."
        return {
            "ok": not any_changed,
            "drift": any_changed,
            "changed": False,
            "files": changed_files,
            "message": msg,
        }

    msg = (
        "KB counts already up to date."
        if not any_changed
        else "KB counts updated."
    )
    return {
        "ok": True,
        "drift": False,
        "changed": any_changed,
        "files": changed_files,
        "message": msg,
    }


# ════════════════════════════════════════════════════════════════════
# MCP registration
# ════════════════════════════════════════════════════════════════════

def register(server) -> None:
    @server.tool(
        name="noctus.dev.kb_sync",
        description=(
            "Native KB-sync verifier + KB-count regenerator (no shell "
            "subprocess). `action='verify'` (default) checks every "
            "CLAUDE.md / CLAUDE/*.md `KNOWLEDGE-BASE/...md` pointer "
            "resolves, every KB doc is indexed in INDEX.md, and the "
            "INDEX.md Layout tree reflects the filesystem (exit 0 synced "
            "/ 1 broken pointer / 2 index|layout drift). "
            "`action='counts'` regenerates the kb-counts marker blocks "
            "(inventory/database/mcp_tools/agent_context_tools); pass "
            "`check=True` for drift-only (no write). See CLAUDE.md § 4."
        ),
    )
    def _kb_sync(action: str = "verify", check: bool = False) -> dict:
        if action == "counts":
            return update_kb_counts(check=check)
        result = verify_kb_sync()
        return dict(result)


__all__ = ["KBSyncResult", "verify_kb_sync", "update_kb_counts", "register"]
