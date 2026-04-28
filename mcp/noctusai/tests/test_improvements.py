"""Tests for the improvements-log generator tool."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.improvements import (
    generate_improvements,
    parse_project,
    render_improvements,
)


def _write_plan(tmp_path: Path, content: str) -> Path:
    plan = tmp_path / "test-plan.md"
    plan.write_text(content, encoding="utf-8")
    return plan


class TestParsing:
    def test_parses_improvements_block(self, tmp_path):
        plan = _write_plan(tmp_path, """# Test Plan

- **Status:** in progress

## 6. Implementation phases

### Phase 1 — Foundation ✅

- [x] did the thing

**Improvements:**
- The X could be refactored to Y.
- Missing edge case for Z.

### Phase 2 — Bodies

- [ ] create openai
""")
        report = parse_project(plan)
        assert report.project_title == "Test Plan"
        assert len(report.phases) == 2
        assert report.phases[0].done is True
        assert "refactored to Y" in (report.phases[0].improvements or "")
        assert "edge case for Z" in (report.phases[0].improvements or "")
        assert report.phases[1].improvements is None

    def test_no_improvements_on_pending_phase(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 — Not done yet

- [ ] task
""")
        report = parse_project(plan)
        assert report.phases[0].improvements is None

    def test_phases_with_improvements_filter(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 — Done with notes ✅

**Improvements:** notes here.

### Phase 2 — Done without notes ✅

### Phase 3 — Pending
""")
        report = parse_project(plan)
        with_imp = report.phases_with_improvements
        without_imp = report.completed_without_improvements
        assert len(with_imp) == 1
        assert with_imp[0].number == 1
        assert len(without_imp) == 1
        assert without_imp[0].number == 2

    def test_multiline_improvements_block(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 — One ✅

**Improvements:**

- First observation about the phase.
- Second observation that spans
  onto a second line.
- Third bullet.

### Phase 2 — Next
""")
        report = parse_project(plan)
        body = report.phases[0].improvements or ""
        assert "First observation" in body
        assert "Second observation" in body
        assert "Third bullet" in body

    def test_extracts_out_of_scope_still_works(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 4. Scope

**Out of scope (deferred):**
- streaming
- token metrics

---

## 6. phases
""")
        report = parse_project(plan)
        assert "streaming" in report.out_of_scope[0]
        assert len(report.out_of_scope) == 2

    def test_no_phases_safe(self, tmp_path):
        plan = _write_plan(tmp_path, "# Empty plan\n\nNothing here.")
        report = parse_project(plan)
        assert report.phases == []
        assert report.all_done is False

    def test_all_status_icons_recognized(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 — Not started

### Phase 2 — In progress ⏳

### Phase 3 — Complete ✅ (shipped yesterday)

### Phase 4 — Blocked ❌
""")
        report = parse_project(plan)
        assert [p.status for p in report.phases] == [
            "pending", "in_progress", "done", "blocked"
        ]

    def test_icon_stripped_from_title(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 — Foundation work ✅ (all green)
""")
        report = parse_project(plan)
        # Title is clean — no icon, no parenthetical.
        assert report.phases[0].title == "Foundation work"
        assert report.phases[0].status == "done"

    def test_icon_before_dash_is_recognized(self, tmp_path):
        """In-use convention across living projects: `### Phase N ✅ — Title`.
        The parser must accept the icon between the number and the dash, not
        only at the end of the title."""
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 ✅ — Foundation work

### Phase 2 ⏳ — In progress work

### Phase 3 ❌ — Blocked work

### Phase 4 — Still pending
""")
        report = parse_project(plan)
        assert [p.status for p in report.phases] == [
            "done", "in_progress", "blocked", "pending"
        ]
        # Titles preserved cleanly.
        assert report.phases[0].title == "Foundation work"

    def test_annotated_improvements_header_is_recognized(self, tmp_path):
        """Living projects use `**Improvements (Phase N capture):**` with an
        annotation explaining which phase the block belongs to. The parser
        must accept the annotated form alongside the bare `**Improvements:**`."""
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 ✅ — Ship

**Improvements (Phase 1 capture):**

- *Observed a cache-warmup race condition.*
- *The logging layer silently dropped debug-level traces.*

### Phase 2 — Pending
""")
        report = parse_project(plan)
        assert report.phases[0].improvements is not None
        assert "cache-warmup race" in report.phases[0].improvements


class TestRendering:
    def test_renders_improvements_section(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 — One ✅

**Improvements:** Refactor the key cache to LRU.
""")
        report = parse_project(plan)
        md = render_improvements(report)
        assert "## Improvements by phase" in md
        assert "Phase 1 — One" in md
        assert "Refactor the key cache" in md

    def test_empty_improvements_section_has_nudge(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 - [ ] Pending
""")
        report = parse_project(plan)
        md = render_improvements(report)
        assert "No improvements recorded yet" in md

    def test_completed_without_improvements_section(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 — Missing notes ✅
""")
        report = parse_project(plan)
        md = render_improvements(report)
        assert "missing an improvements block" in md.lower()
        assert "Phase 1" in md

    def test_does_not_include_preview_of_future_phases(self, tmp_path):
        """Critical: the improvements file is NOT a preview of upcoming work."""
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 — Done ✅

**Improvements:** X.

### Phase 2 — Pending next

### Phase 3 — Pending later
""")
        report = parse_project(plan)
        md = render_improvements(report)
        assert "Pending next" not in md
        assert "Pending later" not in md
        assert "Phase 1 — Done" in md


class TestPublicAPI:
    def test_writes_improvements_file(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 — One ✅

**Improvements:** something to revisit.
""")
        result = generate_improvements(plan, write=True)
        target = tmp_path / "improvements.md"
        assert target.exists()
        assert result["output_path"] == str(target)
        assert result["phases_with_improvements"] == [1]

    def test_write_false_returns_markdown(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 — One ✅

**Improvements:** lesson.
""")
        result = generate_improvements(plan, write=False)
        assert result["output_path"] is None
        assert result["markdown"] is not None
        assert "lesson" in result["markdown"]

    def test_missing_plan_returns_error(self, tmp_path):
        result = generate_improvements(tmp_path / "nope.md", write=True)
        assert "error" in result
        assert result["output_path"] is None

    def test_reports_completed_without_improvements(self, tmp_path):
        plan = _write_plan(tmp_path, """# T

## 6. phases

### Phase 1 — A ✅

**Improvements:** noted.

### Phase 2 — B ✅
""")
        result = generate_improvements(plan, write=False)
        assert result["phases_with_improvements"] == [1]
        assert result["completed_without_improvements"] == [2]
