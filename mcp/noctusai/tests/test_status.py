"""Tests for `tools/status.py` — cross-project state digest."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.status import project_status_digest


class TestProjectStatusDigest:
    def _mk_repo_with_projects(self, projects: list[tuple[str, str]]) -> Path:
        """Create a temp repo with `projects/<slug>/PROJECT.md` files.
        `projects` is a list of (slug, content) tuples.
        """
        tmp = Path(tempfile.mkdtemp(prefix="status_test_"))
        for slug, content in projects:
            (tmp / "projects" / slug).mkdir(parents=True)
            (tmp / "projects" / slug / "PROJECT.md").write_text(content)
        return tmp

    def test_empty_repo_returns_empty(self):
        tmp = Path(tempfile.mkdtemp(prefix="status_empty_"))
        result = project_status_digest(tmp)
        assert result["total"] == 0
        assert result["projects"] == []

    def test_classifies_status_icons(self):
        repo = self._mk_repo_with_projects([
            ("active-one", (
                "# Active\n\n- **Status:** ⏳ executing\n\n"
                "## 6. Implementation phases\n### Phase 1 — Foo\n- [ ] Do A\n"
                "## 11. Change log\n"
            )),
            ("ready-one", (
                "# Ready\n\n- **Status:** 📋 ready\n\n"
                "## 6.\n### Phase 1 — Bar\n- [ ] Do B\n"
                "## 11. Change log\n"
            )),
            ("shipped-one", (
                "# Shipped\n\n- **Status:** ✅ all done 2026-04-28\n\n"
                "## 6.\n### Phase 1 — Baz ✅\n- [x] Done\n"
                "**Improvements:** none.\n"
                "## 11. Change log\n| 2026-04-28 | Phase 1 ✅ shipped | a |\n"
            )),
        ])
        result = project_status_digest(repo)
        assert result["total"] == 3
        slugs = [p["slug"] for p in result["projects"]]
        # Sort order: executing → ready → shipped.
        assert slugs == ["active-one", "ready-one", "shipped-one"]

    def test_subtask_progress_counted(self):
        repo = self._mk_repo_with_projects([("p", (
            "# P\n- **Status:** ⏳\n## 6.\n### Phase 1 — A\n"
            "- [x] Done one\n- [ ] Pending\n- [x] Done two\n"
            "## 11. Change log\n"
        ))])
        result = project_status_digest(repo)
        assert result["projects"][0]["subtask_progress"] == "2/3"

    def test_seed_first_section_detected(self):
        repo = self._mk_repo_with_projects([
            ("with-3a", (
                "# X\n- **Status:** ⏳\n\n## 3a. Seed-first analysis\n\nbody\n\n"
                "## 6.\n### Phase 1 — A\n## 11. Change log\n"
            )),
            ("without-3a", (
                "# Y\n- **Status:** ⏳\n## 6.\n### Phase 1 — A\n## 11. Change log\n"
            )),
        ])
        result = project_status_digest(repo)
        by_slug = {p["slug"]: p for p in result["projects"]}
        assert by_slug["with-3a"]["seed_first_section"] is True
        assert by_slug["without-3a"]["seed_first_section"] is False

    def test_walks_product_scoped_projects(self):
        tmp = Path(tempfile.mkdtemp(prefix="status_prod_"))
        (tmp / "products" / "erp" / "projects" / "thing").mkdir(parents=True)
        (tmp / "products" / "erp" / "projects" / "thing" / "PROJECT.md").write_text(
            "# Thing\n- **Status:** 📋\n## 6.\n### Phase 1 — A\n## 11. Change log\n"
        )
        result = project_status_digest(tmp)
        assert result["total"] == 1
        assert result["projects"][0]["location"] == "products/erp"

    def test_leftmost_icon_wins_over_phase_marker(self):
        """⏳ at the start of status_text must beat a ✅ inside the prose.

        Regression: the old detector iterated ("✅","⏳",...) tuples and
        returned the first match — so "⏳ EXECUTING (Phase 0 ✅, Phase 1 ✅)"
        misclassified as shipped. Every executing project mentions its done
        phases inline, so the bug fired on every active multi-phase project.
        """
        repo = self._mk_repo_with_projects([("active-with-done-phases", (
            "# X\n- **Status:** ⏳ EXECUTING (Phase 0 ✅, Phase 1 ✅, Phase 2 in flight)\n\n"
            "## 6.\n### Phase 1 — A ✅\n- [x] done\n"
            "### Phase 2 — B\n- [ ] todo\n"
            "## 11. Change log\n"
        ))])
        result = project_status_digest(repo)
        proj = result["projects"][0]
        assert proj["status_icon"] == "⏳"
        assert proj["status_bucket"] == "executing"
        assert proj["icon_demoted"] is False  # leftmost was already ⏳

    def test_low_completion_demotes_leftmost_shipped_icon(self):
        """A leftmost ✅ with <75% subtasks done gets demoted to ⏳.

        Regression for `personal-finance-wiring`-shape projects whose
        status_text leads with "Phase 1 ✅ — seed-seam audits complete"
        but only 21 of 72 sub-tasks are ticked — clearly mid-execution.
        """
        # 21/72-ish ratio: 3 done out of 12 = 25%, well below the 0.75 cutoff.
        repo = self._mk_repo_with_projects([("phase1-done-rest-pending", (
            "# Y\n- **Status:** Phase 1 ✅ — seed-seam audits complete; rest pending.\n\n"
            "## 6.\n### Phase 1 — A ✅\n- [x] a\n- [x] b\n- [x] c\n"
            "### Phase 2 — B\n- [ ] d\n- [ ] e\n- [ ] f\n- [ ] g\n- [ ] h\n- [ ] i\n- [ ] j\n- [ ] k\n- [ ] l\n"
            "## 11. Change log\n"
        ))])
        result = project_status_digest(repo)
        proj = result["projects"][0]
        assert proj["status_icon"] == "⏳"
        assert proj["icon_demoted"] is True
        assert proj["subtask_progress"] == "3/12"

    def test_high_completion_keeps_shipped_icon(self):
        """Leftmost ✅ at ≥75% completion stays ✅ (§3a-N/A-litmus carve-out).

        Regression: `pf-metas-seed-wiring`-shape — 16/19 = 84% ticked, the
        3 unticked rows are intentional §3a N/A litmus markers. Must still
        report shipped.
        """
        repo = self._mk_repo_with_projects([("almost-fully-ticked", (
            "# Z\n- **Status:** Done — Phase 0 ✅ + Phase 1+2 (collapsed) ✅ + Phase 3 ✅\n\n"
            "## 6.\n### Phase 1 ✅\n"
            + "".join(f"- [x] task{i}\n" for i in range(16))
            + "- [ ] §3a N/A a\n- [ ] §3a N/A b\n- [ ] §3a N/A c\n"
            "## 11. Change log\n"
        ))])
        result = project_status_digest(repo)
        proj = result["projects"][0]
        assert proj["status_icon"] == "✅"
        assert proj["icon_demoted"] is False
        assert proj["status_bucket"] == "shipped (audit history)"

    def test_no_icon_falls_back_to_subtask_state(self):
        """A status line with no icon at all infers from subtask completion."""
        repo = self._mk_repo_with_projects([
            ("none-with-progress", (
                "# A\n- **Status:** Phase 0 → Phase 1 ready\n\n"
                "## 6.\n### Phase 1 — A\n- [x] a\n- [ ] b\n## 11. Change log\n"
            )),
            ("none-with-zero", (
                "# B\n- **Status:** Concept — interrogation pending.\n\n"
                "## 6.\n### Phase 1 — A\n- [ ] a\n## 11. Change log\n"
            )),
            ("none-fully-done", (
                "# C\n- **Status:** All done.\n\n"
                "## 6.\n### Phase 1 — A\n- [x] a\n## 11. Change log\n"
            )),
        ])
        by_slug = {p["slug"]: p for p in project_status_digest(repo)["projects"]}
        assert by_slug["none-with-progress"]["status_icon"] == "⏳"
        assert by_slug["none-with-zero"]["status_icon"] == "none"
        assert by_slug["none-fully-done"]["status_icon"] == "✅"

    def test_phases_shipped_counts_visible_checkmarks(self):
        """`phases_shipped` reports phase blocks whose header or first lines carry ✅."""
        repo = self._mk_repo_with_projects([("mixed-phases", (
            "# M\n- **Status:** ⏳\n\n"
            "## 6.\n"
            "### Phase 0 — Audit ✅\n- [x] a\n\n"
            "### Phase 1 — Build ✅\n- [x] b\n\n"
            "### Phase 2 — Test\n- [ ] c\n\n"
            "## 11. Change log\n"
        ))])
        proj = project_status_digest(repo)["projects"][0]
        assert proj["phase_count"] == 3
        assert proj["phases_shipped"] == 2

    def test_shipped_unarchived_surfaced_with_nudge(self):
        """A fully-shipped (✅) project still in the live tree is listed in
        `shipped_unarchived` + `next_action` nudges the archive close-out."""
        repo = self._mk_repo_with_projects([
            ("active-one", (
                "# A\n- **Status:** ⏳ executing\n## 6.\n### Phase 1 — A\n- [ ] todo\n## 11. Change log\n"
            )),
            ("shipped-one", (
                "# S\n- **Status:** ✅ all done 2026-04-28\n\n"
                "## 6.\n### Phase 1 — Baz ✅\n- [x] Done\n## 11. Change log\n"
            )),
        ])
        result = project_status_digest(repo)
        assert result["shipped_unarchived"] == ["projects/shipped-one/PROJECT.md"]
        assert "archive" in result["next_action"].lower()
        assert "learn-before-archive" in result["next_action"].lower()

    def test_clean_closeout_when_nothing_shipped(self):
        """No fully-shipped project ⇒ empty list + clean next_action."""
        repo = self._mk_repo_with_projects([("active-one", (
            "# A\n- **Status:** ⏳ executing\n## 6.\n### Phase 1 — A\n- [ ] todo\n## 11. Change log\n"
        ))])
        result = project_status_digest(repo)
        assert result["shipped_unarchived"] == []
        assert "clean" in result["next_action"].lower()

    def test_demoted_shipped_not_flagged_unarchived(self):
        """A leftmost-✅ project demoted to ⏳ (low completion) is NOT a
        close-out candidate — only genuinely-shipped projects are flagged,
        so partially-shipped projects (e.g. waves-done-but-fan-out-pending)
        are never spuriously nagged."""
        repo = self._mk_repo_with_projects([("partial", (
            "# P\n- **Status:** Phase 1 ✅ — rest pending.\n\n"
            "## 6.\n### Phase 1 ✅\n- [x] a\n### Phase 2\n"
            + "".join(f"- [ ] t{i}\n" for i in range(10))
            + "## 11. Change log\n"
        ))])
        result = project_status_digest(repo)
        assert result["shipped_unarchived"] == []
