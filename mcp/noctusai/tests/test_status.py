"""Tests for `tools/status.py` — cross-project state digest."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.status import (
    _collect_status_continuation,
    _STATUS_RE,
    project_status_digest,
)


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

    def test_status_line_shapes_all_parsed(self):
        """`_STATUS_RE` must accept every observed `**Status...**` shape, not
        just the original `- **Status:**` list form.

        Regression: `projects/one-ops-agents`, `edicao-fotos`,
        `olx-portal-leads-ingestion`, and `seed-lift-ke-gap-seams` PROJECT.md
        files were all silently mis-read as `status_icon="none"` with an
        EMPTY `status_text` because the old regex only matched the list
        form — a shipped blockquote-form project became invisible to
        `shipped_unarchived` (the false-green this fix closes)."""
        repo = self._mk_repo_with_projects([
            ("blockquote-form", (
                "# A\n\n> **Status:** Phase A in flight (2026-09-19) · "
                "**Owner:** tech-lead\n\n## 6.\n### Phase 1 — X\n"
                "## 11. Change log\n"
            )),
            ("blockquote-parenthetical", (
                "# B\n\n> **Status (2026-09-16, later):**\n"
                "> - **On `dev`:** some sub-bullet detail.\n\n"
                "## 6.\n### Phase 1 — X\n## 11. Change log\n"
            )),
            ("colon-inside-bold", (
                "# C\n\n> **Status: BUILT + MCP REGISTERED, not merged, "
                "not deployed** (2026-08-17).\n\n"
                "## 6.\n### Phase 1 — X\n## 11. Change log\n"
            )),
            ("blockquote-with-icon", (
                "# D\n\n> **Status:** 📋 filed (N=1 today; lift later).\n\n"
                "## 6.\n### Phase 1 — X\n## 11. Change log\n"
            )),
            ("bare-status-no-marker", (
                "# E\n\n**Status:** ⏳ mid-flight, no list/blockquote marker.\n\n"
                "## 6.\n### Phase 1 — X\n## 11. Change log\n"
            )),
        ])
        by_slug = {p["slug"]: p for p in project_status_digest(repo)["projects"]}

        blockquote = by_slug["blockquote-form"]
        assert blockquote["status_unparsed"] is False
        assert "Phase A in flight" in blockquote["status_text"]

        parenthetical = by_slug["blockquote-parenthetical"]
        assert parenthetical["status_unparsed"] is False
        # Nothing follows "**Status (...):**" on its own line, but the very
        # next line is a `> - ` continuation bullet — recovered as the real
        # status text (see test_multiline_blockquote_status_recovers_from_
        # continuation_bullets for the full edicao-fotos-shaped case).
        assert "On `dev`" in parenthetical["status_text"]

        colon_inside = by_slug["colon-inside-bold"]
        assert colon_inside["status_unparsed"] is False
        assert colon_inside["status_text"] == (
            "BUILT + MCP REGISTERED, not merged, not deployed"
        )

        with_icon = by_slug["blockquote-with-icon"]
        assert with_icon["status_unparsed"] is False
        assert with_icon["status_icon"] == "📋"
        assert with_icon["status_bucket"] == "ready / design-locked"

        bare = by_slug["bare-status-no-marker"]
        assert bare["status_unparsed"] is False
        assert bare["status_icon"] == "⏳"

    def test_multiline_blockquote_status_recovers_from_continuation_bullets(self):
        """Pins `projects/edicao-fotos/PROJECT.md`'s exact shape: a `**Status
        (...):**` header with a parenthetical AND no inline text, followed by
        several `> - **Label:** ...` continuation bullets, followed by
        SIBLING `> **Field:**` metadata lines that are NOT part of status.

        Regression (found on review, 2026-09-20): the header-only capture is
        `""`, and `status_unparsed = m is None` only tested whether the regex
        matched at all — so this shape reported `status_unparsed=False` with
        an EMPTY `status_text`, i.e. a confident-looking "pending / nothing
        happening" read. That is the exact false-green this fix exists to
        remove, and worse than before: it no longer showed up in
        `status_unparsed` either. The fix recovers the continuation bullets
        as the real status text, and would fall back to `status_unparsed`
        if NO continuation bullets followed (a match that captured nothing
        is not a successful read — see `_collect_status_continuation`)."""
        content = (
            "# Edição de Fotos\n\n"
            "> **Status (2026-09-16, later):**\n"
            "> - **On `dev`:** Wave 1 seed organs, S3b `image_edit`.\n"
            "> - **Migrations applied to prod:** Core `046` and SW `121`-`128`.\n"
            "> - **In prod:** the seed code shipped; the engine did not.\n"
            "> - **Not started:** the SW module (W2+), its pages.\n"
            "> - **Blocked:** the OpenAI account has no credits.\n"
            "> **Base:** `7e5f5ad6` (origin/dev at 2026-09-16).\n"
            "> **Spec:** `../../genesis vision/README.md`.\n"
            "> **Approved plan:** `~/.claude/plans/x.md`.\n"
            "> **Shape:** seed organs + a social-wiring module.\n\n"
            "## 6.\n### Phase 1 — X\n## 11. Change log\n"
        )
        repo = self._mk_repo_with_projects([("edicao-fotos-shape", content)])
        result = project_status_digest(repo)
        proj = result["projects"][0]

        # Recovered, not silently empty-and-confident. `status_text` is
        # truncated to 120 chars for display (pre-existing, unrelated to this
        # fix) so only the FIRST couple of bullets survive here — the full,
        # untruncated recovery (including the later bullets + the stop rule)
        # is asserted directly against `_collect_status_continuation` below.
        assert proj["status_unparsed"] is False
        assert "On `dev`" in proj["status_text"]
        assert result["status_unparsed"] == []

        # Full, untruncated recovery + the stop rule: sibling `> **Field:**`
        # metadata lines (Base / Spec / Approved plan / Shape) are NOT status
        # bullets and must not leak into the recovered text.
        m = _STATUS_RE.search(content)
        full_text = _collect_status_continuation(content, m.end())
        assert "Migrations applied to prod" in full_text
        assert "Not started" in full_text
        assert "Blocked" in full_text
        assert "Base" not in full_text
        assert "Approved plan" not in full_text
        assert "Shape" not in full_text

    def test_empty_status_header_with_no_continuation_is_unparsed(self):
        """A `**Status:**` header that matched but captured NOTHING — and has
        no `> - ` continuation bullet after it either — must surface as
        `status_unparsed`, never as a confident empty `none` read. This is
        option 1 of the edicao-fotos fix: a match that captured nothing is
        not a successful read."""
        repo = self._mk_repo_with_projects([("empty-status-no-continuation", (
            "# X\n\n> **Status (2026-09-16, later):**\n\n"
            "Just prose after it, no `> - ` bullets.\n\n"
            "## 6.\n### Phase 1 — X\n## 11. Change log\n"
        ))])
        result = project_status_digest(repo)
        proj = result["projects"][0]
        assert proj["status_unparsed"] is True
        assert proj["status_text"] == ""
        assert result["status_unparsed"] == [
            "projects/empty-status-no-continuation/PROJECT.md"
        ]

    def test_no_status_line_reported_as_unparsed_not_silently_pending(self):
        """A PROJECT.md with NO `**Status:**` line at all (any shape) must
        surface distinctly via `status_unparsed` — never silently fold into
        the same `none`/pending bucket as a confidently-parsed "nothing
        happening" project, and `next_action` must not assert close-out
        cleanliness while it's outstanding."""
        repo = self._mk_repo_with_projects([("no-status-at-all", (
            "# No Status\n\nJust prose, no Status line anywhere.\n\n"
            "## 6.\n### Phase 1 — X\n## 11. Change log\n"
        ))])
        result = project_status_digest(repo)
        proj = result["projects"][0]
        assert proj["status_unparsed"] is True
        assert proj["status_icon"] == "none"
        assert result["status_unparsed"] == ["projects/no-status-at-all/PROJECT.md"]
        assert result["shipped_unarchived"] == []
        assert "clean" not in result["next_action"].lower()
        assert "no-status-at-all" in result["next_action"]

    def test_status_unparsed_empty_when_all_parsed(self):
        """The clean-closeout case still says "clean" when every project's
        Status line parsed (no unparsed entries) — regression guard against
        the new branch swallowing the pre-existing clean message."""
        repo = self._mk_repo_with_projects([("active-one", (
            "# A\n- **Status:** ⏳ executing\n## 6.\n### Phase 1 — A\n- [ ] todo\n## 11. Change log\n"
        ))])
        result = project_status_digest(repo)
        assert result["status_unparsed"] == []
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
