"""Tests for `tools/status.py` — cross-project state digest."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.status import project_status_digest


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
