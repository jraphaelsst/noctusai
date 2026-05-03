"""`noctusai_check_three_way_sync` — verify KB ↔ CLAUDE.md ↔ memory parity.

Closes the gap that `verify-kb-sync.sh` cannot cover (memory lives
outside the repo at `~/.claude/projects/.../memory/`). The three-way-sync
rule (`KB § 01-PHILOSOPHY § Docs stay in sync`) explicitly notes:

> *"`verify-kb-sync.sh` does NOT verify [memory parity]. It's the
> agent's discipline."*

This tool encodes that discipline as a deterministic check.

**Memory directory resolution:**
- Looks for `~/.claude/projects/-Users-rapha-Documents-repository-NoctusAI-noctusai/memory/`
  (the standard location for this repo's auto-memory).
- Falls back to `$NOCTUSAI_MEMORY_DIR` env var if set.
- Returns a no-op result with a warning if neither resolves (different
  agents may use different memory locations; missing memory ≠ failure).

**Checks:**
1. **Memory file present in `MEMORY.md` index?** Every `feedback_*.md`
   in the memory dir must have a row in `MEMORY.md`.
2. **MEMORY.md row file resolves?** Every `[Title](file.md)` link in
   `MEMORY.md` must resolve to an existing file.
3. **Memory entry cites a KB anchor?** Every `feedback_*.md` body should
   include a `KB § ...` reference. The memory rule says "Doc-backed".
4. **CLAUDE.md has a corresponding rule?** Heuristic — look for the
   memory entry's `name:` text or a close keyword in CLAUDE.md.
   Fuzzy by design (CLAUDE.md rules are paraphrased, not verbatim).
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[5]


def _resolve_memory_dir() -> Path | None:
    """Find the memory directory. Returns None if not resolvable."""
    env_dir = os.environ.get("NOCTUSAI_MEMORY_DIR")
    if env_dir:
        candidate = Path(env_dir).expanduser()
        if candidate.exists() and (candidate / "MEMORY.md").exists():
            return candidate

    # Standard path for this repo.
    home = Path.home()
    candidate = home / ".claude" / "projects" / "-Users-rapha-Documents-repository-NoctusAI-noctusai" / "memory"
    if candidate.exists() and (candidate / "MEMORY.md").exists():
        return candidate

    # Last-resort: walk ~/.claude/projects/ for any folder named "memory".
    claude_dir = home / ".claude" / "projects"
    if claude_dir.exists():
        for project_dir in claude_dir.iterdir():
            mem = project_dir / "memory"
            if mem.exists() and (mem / "MEMORY.md").exists():
                return mem
    return None


_FEEDBACK_FRONTMATTER_NAME = re.compile(
    r'^---\s*\n.*?^name:\s*(.+?)\s*$.*?^---',
    re.MULTILINE | re.DOTALL,
)
_KB_ANCHOR_RE = re.compile(r'KB §|`KB §|KNOWLEDGE-BASE/CONTEXT/')
_MEMORY_INDEX_LINK_RE = re.compile(r'\[([^\]]+)\]\((feedback_[^)]+\.md)\)')
_MEMORY_FILE_RE = re.compile(r'^feedback_[a-z0-9_]+\.md$')


def _read_memory_index_links(memory_md: Path) -> dict[str, str]:
    """Parse `MEMORY.md` and return {filename: title} for every memory link."""
    if not memory_md.exists():
        return {}
    content = memory_md.read_text(encoding="utf-8")
    return {
        match.group(2): match.group(1)
        for match in _MEMORY_INDEX_LINK_RE.finditer(content)
    }


def _list_memory_files(memory_dir: Path) -> list[Path]:
    """Return all `feedback_*.md` files in the memory dir, sorted."""
    return sorted(
        f for f in memory_dir.iterdir()
        if f.is_file() and _MEMORY_FILE_RE.match(f.name)
    )


def _extract_frontmatter_name(memory_file: Path) -> str:
    """Extract the `name:` field from a memory file's YAML-ish frontmatter."""
    try:
        content = memory_file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        logger.warning("three_way_sync: cannot read memory file %s (%s)", memory_file, exc)
        return ""
    m = _FEEDBACK_FRONTMATTER_NAME.search(content)
    return m.group(1).strip() if m else ""


def _has_kb_anchor(memory_file: Path) -> bool:
    """Check if a memory file body cites a KB section."""
    try:
        content = memory_file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        logger.warning("three_way_sync: cannot read memory file %s (%s)", memory_file, exc)
        return False
    return bool(_KB_ANCHOR_RE.search(content))


def _claude_md_has_keyword(claude_md_content: str, name: str) -> bool:
    """Heuristic: does CLAUDE.md mention this rule? Uses keyword overlap.

    Memory-rule names are typically declarative ("No silent errors —
    always explicit fix opportunities"). CLAUDE.md rules are bolded
    summaries. We pick the strongest 2-3 keywords from the memory name
    and check if at least one appears in CLAUDE.md (case-insensitive).
    """
    if not name:
        return False
    # Strip common framing words.
    skip = {
        "the", "a", "an", "and", "or", "of", "for", "to", "in", "at",
        "is", "are", "be", "always", "never", "rule", "pattern", "every",
        "across", "tied", "with", "applies", "fires",
    }
    tokens = [
        t.strip("—-,:.()[]").lower()
        for t in name.split()
        if t.strip("—-,:.()[]")
    ]
    keywords = [t for t in tokens if t and t not in skip and len(t) > 3]
    if not keywords:
        return True  # don't false-positive trivial names
    # Look for any 1 of the top 3 keywords.
    haystack = claude_md_content.lower()
    return any(kw in haystack for kw in keywords[:3])


def check_three_way_sync(repo_root: Path | None = None) -> dict:
    """Walk memory + KB + CLAUDE.md and report parity issues.

    Returns:
        ```
        {
          "memory_dir": "<path or null>",
          "checked": int,
          "issues": [{"severity": "...", "file": "...", "issue": "..."}, ...],
          "stats": {
            "memory_files_total": int,
            "memory_files_in_index": int,
            "memory_files_with_kb_anchor": int,
            "memory_files_with_claude_md_keyword": int,
          }
        }
        ```
    """
    root = repo_root or REPO_ROOT
    issues: list[dict] = []

    memory_dir = _resolve_memory_dir()
    if memory_dir is None:
        return {
            "memory_dir": None,
            "checked": 0,
            "issues": [{
                "severity": "warning",
                "file": "<memory>",
                "issue": (
                    "Memory directory not resolvable. Set $NOCTUSAI_MEMORY_DIR "
                    "or ensure `~/.claude/projects/.../memory/` exists. Skipping "
                    "three-way-sync check (not a failure — memory may be on a "
                    "different agent host)."
                ),
            }],
            "stats": {},
        }

    memory_md = memory_dir / "MEMORY.md"
    claude_md_path = root / "CLAUDE.md"
    if not claude_md_path.exists():
        return {
            "memory_dir": str(memory_dir),
            "checked": 0,
            "issues": [{
                "severity": "high",
                "file": "CLAUDE.md",
                "issue": f"CLAUDE.md not found at {claude_md_path}.",
            }],
            "stats": {},
        }
    claude_content = claude_md_path.read_text(encoding="utf-8")
    index_links = _read_memory_index_links(memory_md)
    memory_files = _list_memory_files(memory_dir)

    in_index = 0
    with_kb_anchor = 0
    with_claude_keyword = 0

    # Check 1: every feedback_*.md is in MEMORY.md index.
    for mf in memory_files:
        name_in_index = mf.name in index_links
        if name_in_index:
            in_index += 1
        else:
            issues.append({
                "severity": "high",
                "file": f"~/.claude/.../{mf.name}",
                "issue": (
                    f"Memory file `{mf.name}` exists but is NOT listed in "
                    f"`MEMORY.md`. Add an index entry per the three-way-sync rule."
                ),
            })

        # Check 3: cites a KB anchor.
        if _has_kb_anchor(mf):
            with_kb_anchor += 1
        else:
            issues.append({
                "severity": "warning",
                "file": f"~/.claude/.../{mf.name}",
                "issue": (
                    f"Memory file `{mf.name}` does not cite a KB anchor "
                    f"(`KB § ...` or `KNOWLEDGE-BASE/CONTEXT/...`). Per the "
                    f"three-way-sync rule, memory entries should be doc-backed."
                ),
            })

        # Check 4: CLAUDE.md keyword match (heuristic; warning severity).
        name = _extract_frontmatter_name(mf)
        if _claude_md_has_keyword(claude_content, name):
            with_claude_keyword += 1
        else:
            issues.append({
                "severity": "warning",
                "file": f"~/.claude/.../{mf.name}",
                "issue": (
                    f"Memory file `{mf.name}` (name: \"{name}\") has no obvious "
                    f"keyword match in CLAUDE.md. This is a heuristic — verify "
                    f"manually whether a corresponding rule exists. Per the "
                    f"three-way-sync rule, every memory rule should have a "
                    f"CLAUDE.md pointer."
                ),
            })

    # Check 2: every MEMORY.md link resolves.
    memory_files_set = {mf.name for mf in memory_files}
    for indexed_name, title in index_links.items():
        if indexed_name not in memory_files_set:
            issues.append({
                "severity": "high",
                "file": "MEMORY.md",
                "issue": (
                    f"`MEMORY.md` links to `{indexed_name}` (\"{title}\") but the "
                    f"file does not exist in the memory directory."
                ),
            })

    return {
        "memory_dir": str(memory_dir),
        "checked": len(memory_files),
        "issues": issues,
        "stats": {
            "memory_files_total": len(memory_files),
            "memory_files_in_index": in_index,
            "memory_files_with_kb_anchor": with_kb_anchor,
            "memory_files_with_claude_md_keyword": with_claude_keyword,
        },
    }


def register(server) -> None:
    @server.tool(
        name="noctusai_check_three_way_sync",
        description=(
            "Verify KB ↔ CLAUDE.md ↔ memory parity. Closes the gap that "
            "`verify-kb-sync.sh` cannot cover (memory directory lives outside the repo). "
            "Reports missing index entries, dangling links, missing KB anchors, and "
            "CLAUDE.md keyword mismatches per the three-way-sync rule."
        ),
    )
    def _check_three_way_sync() -> dict:
        return check_three_way_sync()
