"""
improvements tool — auto-generates `improvements.md` in a project's folder.

Concept: while implementing a phase, agents learn things — refactor
candidates, edge cases not covered, performance gotchas, tech debt taken
on, testing gaps. Those findings are captured inline in the project file as a
`**Improvements:**` block per completed phase, and this tool aggregates them
into `improvements.md` next to the project file.

The goal is a feedback loop: future iterations of a phase (rework, v2,
refactor) start from accumulated learnings rather than from scratch.

**What goes in an improvement block:**
  - What could be better about *this phase's* implementation
  - Edge cases discovered but not covered
  - Performance / memory concerns
  - Tech debt taken on deliberately (with rationale)
  - Shortcuts the current implementation took
  - Missing tests / coverage gaps
  - Refactor candidates

**What does NOT go in:**
  - Tasks for future phases (those are already in §6 of the project)
  - Generic "do more tests" — only specific, actionable observations
  - Praise or narration ("this went well")

Parsing rules:
  - Phase header:        `### Phase <N> - [ ] <Title>`  or  `[x]`
  - Improvements block:  `**Improvements:**` followed by free-form text/list
                         until blank line or next `###`
  - Out of scope:        lines under `**Out of scope (…):**` — still carried
  - Open questions:      numbered list under `## 7. Open questions`

No lib-level code: this is a tooling concern, lives inside the MCP dev toolkit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ── Dataclasses ───────────────────────────────────────────────────────

@dataclass
class PhaseSummary:
    number: int
    title: str
    status: str  # "pending" | "in_progress" | "done" | "blocked"
    improvements: Optional[str]  # Free-form text captured from the plan

    @property
    def done(self) -> bool:
        """Back-compat shortcut used by renderer + public API shape."""
        return self.status == "done"


@dataclass
class ImprovementsReport:
    project_path: Path
    project_title: str
    project_status: str
    phases: list[PhaseSummary]
    out_of_scope: list[str]
    open_questions: list[str]

    @property
    def all_done(self) -> bool:
        return all(p.done for p in self.phases) and len(self.phases) > 0

    @property
    def phases_with_improvements(self) -> list[PhaseSummary]:
        return [p for p in self.phases if p.done and p.improvements]

    @property
    def completed_without_improvements(self) -> list[PhaseSummary]:
        return [p for p in self.phases if p.done and not p.improvements]


# ── Parsing ───────────────────────────────────────────────────────────

# Phase header — the whole line after "### Phase N — ". Status icon is
# parsed out of the title separately. Accepts both "-" and "—", and both
# placement conventions (icon between number and dash, OR icon at end of title):
#   "### Phase 5 ✅ — Harden compliance tooling"
#   "### Phase 5 — Harden compliance tooling ✅"
_PHASE_HEADER_RE = re.compile(
    r"^###\s+Phase\s+(\d+)\s*(✅|⏳|❌)?\s*[-—]\s*(.+?)\s*$",
    re.MULTILINE,
)

# Status icons — the icon goes either between the phase number and the dash
# (captured by the phase header regex, group 2) OR at the end of the title
# (captured here). No icon in either spot → pending.
_STATUS_ICON_RE = re.compile(r"(✅|⏳|❌)(?:\s*\(.*?\))?\s*$")
_ICON_TO_STATUS = {"✅": "done", "⏳": "in_progress", "❌": "blocked"}
_PLAN_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_PLAN_STATUS_RE = re.compile(r"^-\s+\*\*Status:\*\*\s+(.+?)\s*$", re.MULTILINE)
# Accept both the vanilla `**Improvements:**` header and the annotated form
# `**Improvements (Phase N capture):**` — both conventions are in use across
# living projects. The optional parenthetical is non-capturing.
_IMPROVEMENTS_RE = re.compile(
    r"\*\*Improvements(?:\s*\([^)]*\))?:\*\*\s*(.+?)(?=\n\s*\n\s*(?:###|---|##)|\Z)",
    re.DOTALL,
)
_OUT_OF_SCOPE_RE = re.compile(
    r"\*\*Out of scope[^*]*\*\*\s*\n(.*?)(?=\n\n---|\n\n##|\Z)",
    re.DOTALL,
)
_OPEN_QUESTIONS_SECTION_RE = re.compile(
    r"##\s*7\.\s*Open questions\s*\n(.*?)(?=\n##\s|\Z)",
    re.DOTALL,
)
_BULLET_LINE_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$", re.MULTILINE)
_NUMBERED_LINE_RE = re.compile(r"^\s*\d+\.\s+(.+?)\s*$", re.MULTILINE)


def _parse_title_and_status(raw_title: str) -> tuple[str, str]:
    """Split a phase title like 'Foundation ✅ (shipped)' into (title, status).

    Status is one of: pending | in_progress | done | blocked.
    No icon → pending.
    """
    raw_title = raw_title.strip()
    m = _STATUS_ICON_RE.search(raw_title)
    if not m:
        return raw_title, "pending"
    status = _ICON_TO_STATUS[m.group(1)]
    # Strip the icon (and any trailing parenthetical comment) from the title.
    clean_title = raw_title[: m.start()].rstrip()
    return clean_title, status


def _extract_phases(content: str) -> list[PhaseSummary]:
    matches = list(_PHASE_HEADER_RE.finditer(content))
    phases: list[PhaseSummary] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end]
        imp = _IMPROVEMENTS_RE.search(body)
        icon_before_dash = m.group(2)  # icon captured between number and dash
        title_part = m.group(3)
        title, end_status = _parse_title_and_status(title_part)
        # Prefer the icon found between number and dash; fall back to end-of-title.
        if icon_before_dash:
            status = _ICON_TO_STATUS[icon_before_dash]
        else:
            status = end_status
        phases.append(
            PhaseSummary(
                number=int(m.group(1)),
                title=title,
                status=status,
                improvements=imp.group(1).strip() if imp else None,
            )
        )
    return phases


def _extract_out_of_scope(content: str) -> list[str]:
    m = _OUT_OF_SCOPE_RE.search(content)
    if not m:
        return []
    return [line.strip() for line in _BULLET_LINE_RE.findall(m.group(1)) if line.strip()]


def _extract_open_questions(content: str) -> list[str]:
    m = _OPEN_QUESTIONS_SECTION_RE.search(content)
    if not m:
        return []
    block = m.group(1)
    items = _NUMBERED_LINE_RE.findall(block)
    if items:
        return [q.strip() for q in items if q.strip()]
    return [q.strip() for q in _BULLET_LINE_RE.findall(block) if q.strip()]


def parse_project(project_path: Path) -> ImprovementsReport:
    content = project_path.read_text(encoding="utf-8")
    title_m = _PLAN_TITLE_RE.search(content)
    status_m = _PLAN_STATUS_RE.search(content)
    return ImprovementsReport(
        project_path=project_path,
        project_title=title_m.group(1).strip() if title_m else project_path.stem,
        project_status=status_m.group(1).strip() if status_m else "unknown",
        phases=_extract_phases(content),
        out_of_scope=_extract_out_of_scope(content),
        open_questions=_extract_open_questions(content),
    )


# ── Rendering ─────────────────────────────────────────────────────────

def render_improvements(report: ImprovementsReport) -> str:
    with_imp = report.phases_with_improvements
    without_imp = report.completed_without_improvements
    lines: list[str] = []

    lines.append(f"# Improvements — {report.project_title}")
    lines.append("")
    lines.append(
        f"> **Auto-generated** from `{report.project_path.name}` by "
        "`python mcp/noctusai/cli.py --improvements <plan.md>`. "
        "Regenerated every time a phase is ticked complete. Do not edit by hand."
    )
    lines.append("")
    lines.append(
        "> This file captures **improvement opportunities discovered while "
        "implementing each phase** — things future iterations of *this* phase "
        "should consider. It is NOT a preview of upcoming phase tasks (those "
        "live in the plan itself). When a phase is refactored or revisited, "
        "open this file first."
    )
    lines.append("")
    lines.append(f"**Plan:** `{report.project_path.name}`")
    lines.append(f"**Plan status:** {report.project_status}")
    lines.append(
        f"**Completed phases:** {sum(1 for p in report.phases if p.done)} "
        f"of {len(report.phases)}."
    )
    lines.append(
        f"**Phases with recorded improvements:** {len(with_imp)} "
        f"of {sum(1 for p in report.phases if p.done)} completed."
    )
    lines.append("")

    # ── Improvements by phase ───────────────────────────
    if with_imp:
        lines.append("## Improvements by phase")
        lines.append("")
        for p in with_imp:
            lines.append(f"### Phase {p.number} — {p.title}")
            lines.append("")
            lines.append(p.improvements or "")
            lines.append("")
    else:
        lines.append("## Improvements by phase")
        lines.append("")
        lines.append(
            "_No improvements recorded yet. As each phase completes, the agent "
            "should append an `**Improvements:**` block to that phase section "
            "in the plan, then re-run this tool._"
        )
        lines.append("")

    # ── Completed without improvements ──────────────────
    if without_imp:
        lines.append("## Completed phases missing an improvements block")
        lines.append("")
        lines.append(
            "These phases shipped without a recorded improvement observation. "
            "Either the agent genuinely had nothing to flag (rare), or they "
            "forgot. Back-fill with an `**Improvements:**` block when possible — "
            "or a line stating \"no improvements identified\" to make the "
            "absence intentional."
        )
        lines.append("")
        for p in without_imp:
            lines.append(f"- Phase {p.number} — {p.title}")
        lines.append("")

    # ── Deferred items (out of scope) ───────────────────
    if report.out_of_scope:
        lines.append("## Deferred items (from §4 Out of scope)")
        lines.append("")
        lines.append(
            "_Work deliberately scoped out of this plan. Track as candidates "
            "for future plans, not as improvements to existing phases._"
        )
        lines.append("")
        for item in report.out_of_scope:
            lines.append(f"- {item}")
        lines.append("")

    # ── Open questions still blocking ───────────────────
    if report.open_questions:
        lines.append("## Open questions still blocking")
        lines.append("")
        for q in report.open_questions:
            lines.append(f"- {q}")
        lines.append("")

    return "\n".join(lines)


# ── Public entry points ───────────────────────────────────────────────

def generate_improvements(project_path: str | Path, *, write: bool = True) -> dict:
    """Parse a plan and (optionally) write `improvements.md` next to it.

    Returns a structured dict with the generated markdown, the destination
    path, and the extracted report — suitable for both CLI and MCP use.
    """
    project_file = Path(project_path).resolve()
    if not project_file.exists():
        return {
            "error": f"Project file not found: {project_file}",
            "output_path": None,
        }

    report = parse_project(project_file)
    md = render_improvements(report)
    output_path: Optional[Path] = None
    if write:
        output_path = project_file.parent / "improvements.md"
        output_path.write_text(md, encoding="utf-8")

    return {
        "project_path": str(project_file),
        "output_path": str(output_path) if output_path else None,
        "markdown": md if not write else None,
        "project_title": report.project_title,
        "project_status": report.project_status,
        "phases": [
            {
                "number": p.number,
                "title": p.title,
                "status": p.status,
                "done": p.done,
                "improvements": p.improvements,
            }
            for p in report.phases
        ],
        "phases_with_improvements": [p.number for p in report.phases_with_improvements],
        "completed_without_improvements": [
            p.number for p in report.completed_without_improvements
        ],
        "out_of_scope": report.out_of_scope,
        "open_questions": report.open_questions,
        "all_done": report.all_done,
    }
