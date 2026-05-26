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


def roster_tree_parity_gaps(root: Path) -> list[str]:
    """Stage-4 keeper predicate (pure, testable). Returns the sorted
    slugs of products that exist on disk (`products/<slug>/backend/app/
    main.py`) but have NO row in the 02-LANDSCAPE.md hand-curated
    `## Products` table. Empty list ⇒ roster covers the tree.

    Codified 2026-05-18: the `social-wiring` omission recurred 3× across
    clean-context onboarding self-tests (hand-table → relocated to a
    frozen generator literal → still missing from the hand-curated
    table). Recurrence rule ⇒ MUST formalize into this deterministic,
    commit-blocking gate so it cannot silently drift a 4th time.
    Colocated regression test: `tests/test_kb_sync.py`.
    """
    landscape = root / "KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md"
    if not landscape.is_file():
        return []
    m = re.search(
        r"^## Products\b(.*?)^## ",
        landscape.read_text(encoding="utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    table = m.group(1) if m else ""
    gaps = [
        mp.parents[2].name
        for mp in (root / "products").glob("*/backend/app/main.py")
        if f"products/{mp.parents[2].name}/" not in table
    ]
    return sorted(gaps)


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
        # Skip illustrative placeholders (`{a,b}.md`, `**/*.md`, `<x>.md`,
        # `X.md`) — share the same exclusion the methodology-ref check uses
        # so section 1 and section 5 stay consistent (DRY).
        if _is_placeholder_ref(ptr):
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

    # ─── 4. Roster-vs-tree parity (Stage-4 keeper, 2026-05-18) ───────
    # Every product on disk MUST have a row in the 02-LANDSCAPE.md
    # hand-curated `## Products` table. The hand table carries curated
    # columns (description/status) so it is NOT auto-generated — this
    # deterministic gate is what guarantees it cannot silently drift
    # (the social-wiring omission recurred 3× across clean-context
    # self-tests → recurrence rule MUST formalize → this check).
    # Missing product = ERROR (commit-blocking): "what products exist"
    # is the load-bearing onboarding fact.
    out.write("Checking 02-LANDSCAPE.md Products table covers every "
              "product on disk...\n")
    for slug in roster_tree_parity_gaps(root):
        err.write(
            f"  ✗ ROSTER DRIFT: products/{slug}/ is on disk "
            f"(backend/app/main.py) but has NO row in 02-LANDSCAPE.md "
            f"`## Products` — add it (the authoritative onboarding "
            f"roster must cover every tracked product).\n"
        )
        errors += 1

    # ─── 5. Methodology doc-reference integrity ───────────────────────
    # Scans CLAUDE.md + CLAUDE/**/*.md + .claude/agents/*.md + all KB
    # docs for `KNOWLEDGE-BASE/…md` literals and `KB § …md` shorthands;
    # excludes placeholders (<x>, X.md, **, etc.); wikilinks [[…]] are
    # advisory only (forward-refs allowed per CLAUDE.md). Reports any
    # ref whose target does not resolve in the KB index.
    out.write("Checking methodology surfaces for broken KB doc refs "
              "(KB § shorthand + literal + .claude/agents + KB→KB)...\n")
    for gap in methodology_reference_gaps(root):
        err.write(
            f"  ✗ BROKEN: {gap} (methodology surface references a KB "
            f"doc that doesn't exist — fix or add the target file)\n"
        )
        errors += 1

    # ─── 5. Summary ──────────────────────────────────────────────────
    out.write("\n")
    if errors == 0 and warnings == 0:
        out.write(
            "✓ KB sync OK — all CLAUDE.md pointers resolve, all KB "
            "docs indexed, Layout tree current, roster covers the tree.\n"
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
# methodology_reference_gaps — cross-surface KB-ref integrity gate
# ════════════════════════════════════════════════════════════════════

# Regex: literal backtick-quoted KNOWLEDGE-BASE/<path>.md
_LIT_REF_RE = re.compile(r"`(KNOWLEDGE-BASE/[^`]+\.md)`")

# Regex: shorthand `KB § <path-ending-in-.md>` (stops at .md; strips
# any trailing " § Section" anchor that follows the .md suffix)
_KB_SHORT_RE = re.compile(r"`KB § ([^`\n]+?\.md)")

# Placeholder chars / single-uppercase-stem test — skip illustrative refs.
# Examples:  `KB § INTEGRATIONS/<x>.md`  `KB § PATTERNS/X.md`
#            `KNOWLEDGE-BASE/**/*.md`
_PLACEHOLDER_CHARS = frozenset("<>{}*")

def _is_placeholder_ref(ref: str) -> bool:
    """Return True if *ref* looks like an illustrative doc example, not a
    real pointer.  Two tests (both are OR — either alone → skip):

    1. The ref string contains any of ``< > { } *``.
    2. The basename stem (before ``.md``) is a single uppercase letter.

    These match patterns like ``KB § INTEGRATIONS/<x>.md``,
    ``KB § PATTERNS/X.md``, ``KNOWLEDGE-BASE/**/*.md``.
    """
    if any(c in ref for c in _PLACEHOLDER_CHARS):
        return True
    # e.g. "X.md" or "PATTERNS/X.md" → stem is "X" (single uppercase letter)
    stem = ref.rstrip("/").rsplit("/", 1)[-1]
    if stem.endswith(".md"):
        stem = stem[:-3]
    if re.fullmatch(r"[A-Z]", stem):
        return True
    return False


def methodology_reference_gaps(root: Path) -> list[str]:
    """Pure predicate: return sorted ``"<surface-relpath>: <bad-ref>"``
    strings for every unresolved, non-placeholder KB reference found in
    the methodology surfaces.

    **Surfaces scanned (in-repo only):**
      * ``CLAUDE.md``
      * ``CLAUDE/**/*.md``
      * ``.claude/agents/*.md``
      * every ``KNOWLEDGE-BASE/**/*.md``

    Memory files are deliberately excluded — they live outside the repo
    and the advisory ``check_three_way_sync`` owns that surface.

    **Reference forms recognised (hard/blocking):**
      (a) literal backtick-quoted  ``KNOWLEDGE-BASE/<path>.md``
      (b) shorthand  ``KB § <ref>`` where *<ref>* ends at the first
          ``.md``; any trailing ``§ Section`` anchor is ignored.

    **Wikilinks** (``[[…]]``) are NOT included — CLAUDE.md documents
    these as allowed forward-refs ("worth writing later, not an error").

    **Resolution** — a ref resolves if ANY of:
      * ``KNOWLEDGE-BASE/<ref>`` is a file
      * ``KNOWLEDGE-BASE/CONTEXT/<ref>`` is a file
      * some KB rel-posix path equals ``<ref>`` or ends with ``/<ref>``
      * ``<ref>``'s basename is in the KB basename set

    Returns an empty list when all refs resolve (clean).
    """
    # Build KB index.
    kb_dir = root / "KNOWLEDGE-BASE"
    if not kb_dir.is_dir():
        return []

    kb_rel: list[str] = []    # relative-to-KB posix, e.g. "CONTEXT/PATTERNS/x.md"
    kb_base: set[str] = set()  # basenames, e.g. {"x.md", "branching.md", ...}
    for p in kb_dir.rglob("*.md"):
        if not p.is_file():
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        rel = p.relative_to(kb_dir).as_posix()
        kb_rel.append(rel)
        kb_base.add(p.name)

    def _resolves(ref: str) -> bool:
        """True iff ref (path after KNOWLEDGE-BASE/) resolves against the index."""
        ref = ref.strip().lstrip("/")
        # 1. Exact match under KNOWLEDGE-BASE/ or KNOWLEDGE-BASE/CONTEXT/
        for cand in (ref, f"CONTEXT/{ref}"):
            if (kb_dir / cand).is_file():
                return True
        # 2. Suffix match against any kb rel-posix path
        for rel in kb_rel:
            if rel == ref or rel.endswith("/" + ref):
                return True
        # 3. Basename fallback
        return ref.split("/")[-1] in kb_base

    # Collect surfaces.
    surfaces: list[Path] = []
    # CLAUDE.md
    claude_md = root / "CLAUDE.md"
    if claude_md.is_file():
        surfaces.append(claude_md)
    # CLAUDE/**/*.md
    claude_dir = root / "CLAUDE"
    if claude_dir.is_dir():
        for p in claude_dir.rglob("*.md"):
            if p.is_file() and not any(
                part.startswith(".") for part in p.relative_to(root).parts
            ):
                surfaces.append(p)
    # .claude/agents/*.md
    agents_dir = root / ".claude" / "agents"
    if agents_dir.is_dir():
        for p in sorted(agents_dir.glob("*.md")):
            if p.is_file():
                surfaces.append(p)
    # .claude/skills/*/SKILL.md  (added 2026-05-25, harness-agents-skills:
    # the new always-on procedure surface; broken KB pointers in skill bodies
    # were previously silent and only surface at recall time.)
    skills_dir = root / ".claude" / "skills"
    if skills_dir.is_dir():
        for p in sorted(skills_dir.glob("*/SKILL.md")):
            if p.is_file():
                surfaces.append(p)
    # KNOWLEDGE-BASE/**/*.md
    for p in kb_dir.rglob("*.md"):
        if p.is_file() and not any(
            part.startswith(".") for part in p.relative_to(root).parts
        ):
            surfaces.append(p)

    gaps: list[str] = []
    for surface in surfaces:
        try:
            text = surface.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        try:
            rel_surface = str(surface.relative_to(root))
        except ValueError:
            rel_surface = surface.name

        # (a) literal KNOWLEDGE-BASE/<path>.md
        for m in _LIT_REF_RE.finditer(text):
            raw = m.group(1)
            ref = raw[len("KNOWLEDGE-BASE/"):]
            if _is_placeholder_ref(ref):
                continue
            if not _resolves(ref):
                gaps.append(f"{rel_surface}: `{raw}`")

        # (b) shorthand KB § <ref>
        for m in _KB_SHORT_RE.finditer(text):
            ref = m.group(1)
            if _is_placeholder_ref(ref):
                continue
            if not _resolves(ref):
                gaps.append(f"{rel_surface}: `KB § {ref}`")

    return sorted(set(gaps))


# ════════════════════════════════════════════════════════════════════
# update_kb_counts — native port of scripts/update-kb-counts.py
# ════════════════════════════════════════════════════════════════════

def _products() -> list[tuple[str, str]]:
    """Product roster — DERIVED from the canonical `start.sh` registry via
    `parse_products_registry()` (the keeper-mandated source —
    `feedback_hardcoded_product_slug_set_keeper`: never freeze a ≥3-slug
    literal). The prior frozen `_PRODUCTS` literal silently omitted
    `social-wiring` → the "auto-derived single source of truth" the docs
    pointed at was itself stale (2026-05-18 clean-context self-test, 2nd
    pass). Deriving makes the roster self-healing for every future
    product. No silent fallback: an unreadable registry RAISES, never
    renders a silently-truncated roster (no-silent-errors)."""
    from noctusai_lib.config.cors_registry import parse_products_registry

    entries = parse_products_registry()
    if not entries:
        raise RuntimeError(
            "parse_products_registry() returned no products — start.sh "
            "registry unreadable; refusing to render a silently-empty "
            "product roster (no-silent-errors)."
        )
    return [
        (e["slug"].replace("-", " ").title(), f"products/{e['slug']}")
        for e in entries
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
    """Count registered MCP tools across the hierarchical ``tools/`` package.

    Restructure-proof: the canonical registration idiom is one
    ``@server.tool`` decorator per tool (FastMCP), plus legacy ``_tool(``
    alias registrations. The old counter scanned flat ``_tool(`` in
    ``server.py``; the 2026-05 scripts-mcp-absorption restructure moved
    registration into ``tools/**`` modules (``server.py`` now just calls
    ``register_all``), so the old pattern returned 0 — a doc-code-coherence
    drift surfaced by the 2026-05-18 clean-context onboarding self-test and
    fixed in-flight. Counting the decorator (exactly one per tool) is the
    stable invariant regardless of where within ``tools/`` a tool lives.
    """
    tools_dir = repo / "mcp" / "noctusai" / "tools"
    if not tools_dir.is_dir():
        return 0
    pat = re.compile(r"^\s*(?:@server\.tool\b|_tool\()", re.MULTILINE)
    total = 0
    for py in tools_dir.rglob("*.py"):
        if ".venv" in py.parts or "__pycache__" in py.parts:
            continue
        try:
            total += len(pat.findall(py.read_text(encoding="utf-8")))
        except OSError:
            continue
    return total


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
    for name, path in _products():
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
    # DERIVED from the real per-schema table counts — never a frozen
    # schema literal (the prior list silently dropped `social_wiring`,
    # same drift class as _products()). `public` first, rest sorted;
    # nothing present in counts is ever silently omitted.
    ordered = ["public"] + sorted(s for s in counts if s != "public")
    schemas_line = " + ".join(f"`{s}`" for s in ordered if s in counts)
    return (
        f"- **Schemas ({len([s for s in ordered if s in counts])}):** {schemas_line}.\n"
        f"- **Tables: {total}** distributed across the schemas.\n"
    )


def _render_mcp_tools(repo: Path) -> str:
    n = _count_mcp_tools(repo)
    return f"**{n} tools total** (auto-counted from `mcp/noctusai/tools/`).\n"


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


__all__ = [
    "KBSyncResult",
    "verify_kb_sync",
    "update_kb_counts",
    "methodology_reference_gaps",
    "register",
]
