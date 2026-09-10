"""`check_every_test_file_is_gated` — the OPEN-WORLD member of the
"a suite nobody runs" keeper family.

WHY A THIRD ONE IS THE RIGHT SHAPE. The two existing keepers are closed-world:
`check_ci_test_matrix_coverage` polices `products/*` and
`check_seed_test_root_ci_coverage` polices `seed/*`. Each can only ask "is this
KNOWN root wired?", which is exactly why every gap in this family was found by
ACCIDENT rather than by a gate:

    2026-08-13  igig/orbity/seed product suites   never in the matrix
    2026-09-09  seed backend x2 + seed/lib FE     4215 tests, no job
    2026-09-10  dev_team + 14 connectors + ...    714 tests, no job

This one asks the inverse question — given every test file git tracks, is there
anywhere it could hide? — and on its first run it immediately found a root that
three rounds of manual auditing had missed AND that the seed keeper had
positively written off (see `TestTheSeedFrontendMiss`).

→ KB § PATTERNS/devops/product-lockfile-and-slug-drift.md
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_every_test_file_is_gated,
    check_seed_test_root_ci_coverage,
)

REPO = Path(__file__).resolve().parents[3]


def _git_repo(root: Path) -> None:
    """A real git repo — the keeper reads `git ls-files`, deliberately, so the
    fixture has to actually track files rather than just create them."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)


def _track(root: Path, rel: str, body: str = "def test_x(): assert True\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    subprocess.run(["git", "-C", str(root), "add", "-f", rel], check=True)


class TestCheckEveryTestFileIsGated:
    """Canonical `Test<detector>` name — the meta-keeper matches on it."""

    def test_a_test_file_outside_every_gated_area_is_flagged(self, tmp_path):
        _git_repo(tmp_path)
        _track(tmp_path, "tools/newthing/tests/test_it.py")

        issues = check_every_test_file_is_gated(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"
        assert "tools/newthing/tests" in issues[0]["file"]

    def test_a_gated_area_is_clean(self, tmp_path):
        _git_repo(tmp_path)
        _track(tmp_path, "dev_team/tests/test_it.py")
        _track(tmp_path, "products/foo/backend/tests/test_it.py")
        _track(tmp_path, "mcp/trello/tests/test_smoke.py")

        assert check_every_test_file_is_gated(tmp_path) == []

    def test_a_new_connector_is_covered_by_pattern_not_by_a_list(self, tmp_path):
        """`tooling-tests` derives its connector list at runtime from git, so a
        brand-new connector must be covered WITHOUT anyone editing a list —
        that is the whole point of deriving it."""
        _git_repo(tmp_path)
        _track(tmp_path, "mcp/brand_new_vendor/tests/test_smoke.py")

        assert check_every_test_file_is_gated(tmp_path) == []

    def test_vendored_third_party_suites_are_never_ours(self, tmp_path):
        """A filesystem walk once reported `dev_team` as having 158 test files;
        151 of them were libcst/gitdb suites inside `.venv/`. Tracked-only plus
        this filter is what keeps the count honest."""
        _git_repo(tmp_path)
        _track(tmp_path, "dev_team/.venv/lib/python3.11/site-packages/libcst/tests/test_x.py")

        assert check_every_test_file_is_gated(tmp_path) == []

    def test_a_source_module_named_test_something_is_not_a_suite(self, tmp_path):
        """`mcp/noctusai/tools/noctus/dev/test_seam_guard.py` is the PreToolUse
        hook IMPLEMENTATION — production code named for its subject. Flagging it
        would train people to ignore this keeper."""
        _git_repo(tmp_path)
        _track(tmp_path, "mcp/noctusai/tools/noctus/dev/test_seam_guard.py", "def deny(): ...\n")

        assert check_every_test_file_is_gated(tmp_path) == []

    def test_frontend_specs_count_too(self, tmp_path):
        _git_repo(tmp_path)
        _track(tmp_path, "somewhere/ui/Widget.test.tsx", "test('x', () => {});\n")

        issues = check_every_test_file_is_gated(tmp_path)
        assert len(issues) == 1, issues


class TestTheSeedFrontendMiss:
    """🔴 The self-correction this keeper produced on its first run.

    `check_seed_test_root_ci_coverage` shipped 2026-09-09 with a frontend
    predicate that globbed only `frontend/src/`. `seed/framework/frontend` keeps
    all 8 of its spec files under `frontend/tests/`, so the predicate returned
    "no specs" and the root was recorded as legitimately ungated — in the job
    comment AND in the KB. 55 tests, never run, with a keeper apparently
    agreeing.

    A predicate that only looks where it expects reports the absence it assumed.
    """

    def test_seed_frontend_specs_under_tests_are_required(self, tmp_path):
        (tmp_path / "seed/framework/frontend/tests").mkdir(parents=True)
        (tmp_path / "seed/framework/frontend/tests/layout.test.tsx").write_text(
            "test('x', () => {});\n"
        )
        (tmp_path / ".github/workflows").mkdir(parents=True)
        (tmp_path / ".github/workflows/test.yml").write_text(
            "name: T\non: {push: {branches: [dev]}}\njobs: {}\n"
        )

        issues = check_seed_test_root_ci_coverage(tmp_path)
        assert [i["file"] for i in issues] == ["seed/framework/frontend"], (
            "specs under frontend/tests/ must count — globbing only src/ is the bug"
        )

    def test_the_live_repo_now_gates_it(self):
        assert check_seed_test_root_ci_coverage(REPO) == []


class TestLiveRepo:
    def test_the_real_repo_is_clean(self):
        """The gate must hold on the tree that ships it."""
        assert check_every_test_file_is_gated(REPO) == []
