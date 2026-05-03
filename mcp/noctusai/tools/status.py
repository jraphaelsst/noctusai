"""`noctusai_status` — cross-project state digest.

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
    seed_first_section: bool
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
            "seed_first_section": self.seed_first_section,
            "flags": self.flags,
        }


_STATUS_RE = re.compile(
    r"^- \*\*Status:\*\*\s*(.*)$",
    re.MULTILINE,
)
_PHASE_HEADER_RE = re.compile(r'^### Phase\s+(\d+)\b', re.MULTILINE)
_SUBTASK_RE = re.compile(r'^[ \t]*-\s*\[([ x])\]\s', re.MULTILINE)
_SEED_FIRST_RE = re.compile(r'^## 3a\.', re.MULTILINE)
_DATE_RE = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')


def _detect_status_icon(status_text: str) -> str:
    """Pick the dominant icon from the §status line."""
    for icon in ("✅", "⏳", "❌", "🅿️", "📋"):
        if icon in status_text:
            return icon
    return "none"


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
    status_icon = _detect_status_icon(status_text)

    # Sub-tasks: across all phase blocks (whole §6 essentially).
    subtasks = _SUBTASK_RE.findall(content)
    subtasks_total = len(subtasks)
    subtasks_done = sum(1 for s in subtasks if s == "x")

    # Phase count.
    phases = _PHASE_HEADER_RE.findall(content)
    phase_count = len(phases)

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
        seed_first_section=seed_first,
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
