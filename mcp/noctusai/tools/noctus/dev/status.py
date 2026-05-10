"""`noctus.dev.status` — cross-project state digest.

Replaces the multi-grep ritual ("what's still active? what's parked?
what's next?") that runs every "what's left of value" question. Walks
every PROJECT.md across the three valid locations + emits a summary.

**Output shape (per project):**
- `slug` — project slug (folder name).
- `location` — `root` / `products/<product>` / `core` (where it lives).
- `status_icon` — `✅` shipped / `⏳` partial / `❌` blocked / `🅿️` parked / `📋` ready / `none` pending.
- `last_updated` — ISO date from §11 Change Log latest row (best-effort regex).
- `subtask_progress` — "X of Y" sub-tasks ticked across all phases.
- `phase_count` — total `### Phase N` headers.
- `seed_first_section` — boolean (§3a present?).
- `flags` — list of issues found by sibling detectors (`check_phase_state_consistency`, `check_clean_folder_violations` once shipped).

**Sort order:** active first (`⏳`/`📋`), then parked, then blocked, then
shipped (audit history at the bottom). Most-recently-updated within
each bucket. Useful for "next likely to execute" picking.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from workspace import get_workspace_root

logger = logging.getLogger(__name__)

# Workspace-aware: walks up from cwd looking for `.noctusai-workspace`
# marker. Falls back to file-relative noc root if no marker found.
# See mcp/noctusai/workspace.py + KB § PATTERNS/seed-workspace.md.
REPO_ROOT = get_workspace_root()


# Reuse the project finder from compliance.py to avoid duplicating the
# three-location walk. Lazy-import to dodge circular-import risk if
# compliance.py grows to import status (unlikely but defensive).
def _find_all_project_md(root: Path) -> list[Path]:
    from .compliance import _find_all_project_md as _impl  # type: ignore
    return _impl(root)


_STATUS_ICONS_ORDER: list[str] = ["⏳", "📋", "🅿️", "❌", "✅", "none"]
_BUCKET_LABEL = {
    "⏳": "executing",
    "📋": "ready / design-locked",
    "🅿️": "parked",
    "❌": "blocked",
    "✅": "shipped (audit history)",
    "none": "pending",
}


@dataclass
class ProjectSummary:
    slug: str
    location: str
    relative_path: str
    status_icon: str
    status_text: str  # raw status text from `**Status:**` line
    last_updated: str | None
    subtasks_total: int
    subtasks_done: int
    phase_count: int
    phases_shipped: int
    seed_first_section: bool
    icon_demoted: bool  # true when ✅ → ⏳ subtask-sanity demotion fired
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        progress = (
            f"{self.subtasks_done}/{self.subtasks_total}"
            if self.subtasks_total else "n/a"
        )
        return {
            "slug": self.slug,
            "location": self.location,
            "relative_path": self.relative_path,
            "status_icon": self.status_icon,
            "status_bucket": _BUCKET_LABEL.get(self.status_icon, "unknown"),
            "status_text": self.status_text,
            "last_updated": self.last_updated,
            "subtask_progress": progress,
            "phase_count": self.phase_count,
            "phases_shipped": self.phases_shipped,
            "seed_first_section": self.seed_first_section,
            "icon_demoted": self.icon_demoted,
            "flags": self.flags,
        }


_STATUS_RE = re.compile(
    r"^- \*\*Status:\*\*\s*(.*)$",
    re.MULTILINE,
)
_PHASE_HEADER_RE = re.compile(r'^### Phase\s+(\d+)\b', re.MULTILINE)
_PHASE_SPLIT_RE = re.compile(r'(?=^### Phase\s+\d+\b)', re.MULTILINE)
_SUBTASK_RE = re.compile(r'^[ \t]*-\s*\[([ x])\]\s', re.MULTILINE)
_SEED_FIRST_RE = re.compile(r'^## 3a\.', re.MULTILINE)
_DATE_RE = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')

# Subtask-completion threshold below which a leftmost-✅ status icon is
# treated as a false positive and demoted to ⏳. 0.75 leaves room for the
# §3a-N/A-litmus carve-out (3 of 19 unticked = 84% still reads as shipped)
# while catching 21/72-shape false positives. See KB §11.3.
_SHIPPED_SUBTASK_THRESHOLD = 0.75


def _detect_status_icon(
    status_text: str,
    subtasks_done: int = 0,
    subtasks_total: int = 0,
) -> tuple[str, bool]:
    """Pick the dominant project-level status icon.

    Returns `(icon, demoted)` — `demoted` is True iff a leftmost-✅ was
    overridden by the subtask-sanity check.

    The previous detector iterated a fixed tuple `("✅", "⏳", ...)` and
    returned the first match in `status_text`, so `✅` always beat `⏳` —
    every executing project mentions its done phases as "Phase X ✅" inside
    the status prose, producing systematic false positives in the shipped
    bucket. The fix runs two complementary checks:

    1. **Leftmost icon wins.** Convention is `**Status:** <icon> <description>`,
       so position carries the signal — pick the icon with the smallest
       index in `status_text`.
    2. **Subtask-sanity demotion.** When the leftmost icon is `✅` but
       subtask completion is below `_SHIPPED_SUBTASK_THRESHOLD`, demote to
       `⏳`. Catches "Phase 1 ✅ — Phase 2 pending" / "Tier 2 ✅ ..." shapes
       that read as shipped textually but are clearly mid-execution.
    3. **No-icon fallback.** Older projects predate the icon convention —
       infer from subtask state (all-done → ✅, partial → ⏳, none → none).

    See KB § CONTEXT/PATTERNS/project-execution.md §11.3 for the heuristic
    rationale + slip-history.
    """
    icon_positions: dict[str, int] = {}
    for icon in ("✅", "⏳", "❌", "🅿️", "📋"):
        idx = status_text.find(icon)
        if idx >= 0:
            icon_positions[icon] = idx

    if not icon_positions:
        if subtasks_total == 0:
            return ("none", False)
        if subtasks_done == subtasks_total:
            return ("✅", False)
        if subtasks_done > 0:
            return ("⏳", False)
        return ("none", False)

    leftmost = min(icon_positions.items(), key=lambda kv: kv[1])[0]

    if leftmost == "✅" and subtasks_total > 0:
        completion = subtasks_done / subtasks_total
        if completion < _SHIPPED_SUBTASK_THRESHOLD:
            return ("⏳", True)

    return (leftmost, False)


def _count_shipped_phases(content: str) -> int:
    """Count `### Phase N` blocks whose header line OR first inner status
    line carries `✅`. Used alongside the top-level icon so callers can see
    phase-level shipping independently of the overall status bucket.
    """
    shipped = 0
    for chunk in _PHASE_SPLIT_RE.split(content):
        if not chunk.startswith("### Phase"):
            continue
        # Look at the header line + the next ~3 non-empty lines (catches
        # `**Status:** ✅` immediately under the header).
        head = "\n".join(chunk.splitlines()[:5])
        if "✅" in head:
            shipped += 1
    return shipped


def _location_label(relative_path: str) -> str:
    if relative_path.startswith("products/"):
        return f"products/{relative_path.split('/', 2)[1]}"
    if relative_path.startswith("core/"):
        return "core"
    if relative_path.startswith("projects/"):
        return "root"
    return "unknown"


def _summarize_one(project_md: Path, root: Path, flags_per_project: dict) -> ProjectSummary:
    content = project_md.read_text(encoding="utf-8")
    try:
        relative = str(project_md.relative_to(root))
    except ValueError:
        logger.warning("status: PROJECT.md outside repo root, using absolute: %s", project_md)
        relative = str(project_md)

    parent = project_md.parent
    slug = parent.name

    # Status: first `- **Status:**` line in the doc.
    m = _STATUS_RE.search(content)
    status_text = m.group(1).strip() if m else ""

    # Sub-tasks: across all phase blocks (whole §6 essentially).
    subtasks = _SUBTASK_RE.findall(content)
    subtasks_total = len(subtasks)
    subtasks_done = sum(1 for s in subtasks if s == "x")

    # Status icon needs subtask context for the sanity-check demotion.
    status_icon, icon_demoted = _detect_status_icon(
        status_text, subtasks_done, subtasks_total
    )

    # Phase count + phases visibly shipped.
    phases = _PHASE_HEADER_RE.findall(content)
    phase_count = len(phases)
    phases_shipped = _count_shipped_phases(content)

    # §3a present?
    seed_first = bool(_SEED_FIRST_RE.search(content))

    # Last updated: last date from §11 — find from the END of the file.
    last_updated: str | None = None
    changelog_idx = content.rfind("## 11.")
    if changelog_idx == -1:
        changelog_idx = content.rfind("# Change log")
    haystack = content[changelog_idx:] if changelog_idx != -1 else content
    dates = _DATE_RE.findall(haystack)
    if dates:
        last_updated = max(dates)

    return ProjectSummary(
        slug=slug,
        location=_location_label(relative),
        relative_path=relative,
        status_icon=status_icon,
        status_text=status_text[:120] + ("…" if len(status_text) > 120 else ""),
        last_updated=last_updated,
        subtasks_total=subtasks_total,
        subtasks_done=subtasks_done,
        phase_count=phase_count,
        phases_shipped=phases_shipped,
        seed_first_section=seed_first,
        icon_demoted=icon_demoted,
        flags=flags_per_project.get(relative, []),
    )


def project_status_digest(repo_root: Path | None = None) -> dict:
    """Walk every PROJECT.md and emit a sorted digest.

    Returns:
        `{"projects": [<ProjectSummary>...], "buckets": {bucket: count}}`
    """
    root = repo_root or REPO_ROOT

    # Pull sibling-detector flags so an issue against a project surfaces in its row.
    # Lazy-imported to avoid circular dependencies during refactors.
    from .compliance import check_phase_state_consistency
    flags_per_project: dict[str, list[str]] = {}
    for issue in check_phase_state_consistency(root):
        rel = issue.get("file") or ""
        flags_per_project.setdefault(rel, []).append(
            f"phase-state: {issue.get('issue', '')[:120]}"
        )

    summaries = [
        _summarize_one(p, root, flags_per_project)
        for p in _find_all_project_md(root)
    ]

    # Sort: bucket-first, then most-recent last_updated within bucket (descending).
    bucket_order = {icon: i for i, icon in enumerate(_STATUS_ICONS_ORDER)}
    summaries.sort(
        key=lambda s: (
            bucket_order.get(s.status_icon, 99),
            -(_date_sort_key(s.last_updated)),
            s.slug,
        )
    )

    buckets: dict[str, int] = {label: 0 for label in _BUCKET_LABEL.values()}
    for s in summaries:
        buckets[_BUCKET_LABEL.get(s.status_icon, "unknown")] += 1

    return {
        "projects": [s.to_dict() for s in summaries],
        "buckets": buckets,
        "total": len(summaries),
    }


def _date_sort_key(date_str: str | None) -> int:
    """Convert ISO date to a sortable int. Missing dates sort last."""
    if not date_str:
        return -10**9
    try:
        return int(date_str.replace("-", ""))
    except ValueError:
        logger.warning("status: malformed date string %r, sorting last", date_str)
        return -10**9


def register(server) -> None:
    @server.tool(
        name="noctus.dev.status",
        description=(
            "Cross-project state digest. Walks every PROJECT.md across `projects/`, "
            "`products/*/projects/`, `core/projects/` and returns status icon "
            "(leftmost-in-status_text with subtask-sanity demotion, see KB §11.3), "
            "sub-task progress, phase count + visibly-shipped-phase count, "
            "last-updated date, §3a presence, `icon_demoted` boolean (true when a "
            "false-positive ✅ was demoted to ⏳), and phase-state-detector flags. "
            "Sorted by bucket (executing → ready → parked → blocked → shipped)."
        ),
    )
    def _status() -> dict:
        return project_status_digest()
