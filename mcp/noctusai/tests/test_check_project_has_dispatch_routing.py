"""Tests for `check_project_has_dispatch_routing` Stage-4 keeper.

Predicate: PROJECT.md contains real §6 phase headers (`### Phase \\d+`)
AND does NOT contain a `## 4a` Dispatch routing section. Grandfathered
for projects whose PROJECT.md first-commit predates the rule's birthday
(2026-05-26).

KB § PATTERNS/common/dispatch-with-project-and-notes.md.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from tools.noctus.dev import compliance


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)


def _commit_file(repo: Path, rel_path: str, content: str, date_iso: str | None = None) -> None:
    fp = repo / rel_path
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content)
    subprocess.run(["git", "add", rel_path], cwd=repo, check=True)
    env = None
    if date_iso:
        import os
        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = date_iso
        env["GIT_COMMITTER_DATE"] = date_iso
    subprocess.run(
        ["git", "commit", "-q", "-m", f"add {rel_path}"],
        cwd=repo, check=True, env=env,
    )


# Sentinel PROJECT.md bodies
_PROJECT_WITH_PHASES_NO_4A = """# Test — Project Document

## 1. Context & Purpose
Stuff.

## 6. Implementation phases

### Phase 1 — Foundation
- [ ] task
"""

_PROJECT_WITH_PHASES_AND_4A = """# Test — Project Document

## 1. Context & Purpose
Stuff.

## 4a. Dispatch routing (REQUIRED — the slice-to-engineer map)

| Slice | Lens | Files |
|---|---|---|
| W1 | backend-engineer | foo.py |

## 6. Implementation phases

### Phase 1 — Foundation
- [ ] task
"""

_PROJECT_NO_PHASES = """# Test — Project Document

## 1. Context & Purpose
Pure design doc; no §6 phases yet.

## 5. Architecture
Some tables.
"""


class TestProjectHasDispatchRouting:
    def test_silent_when_no_projects(self, tmp_path):
        _git_init(tmp_path)
        issues = compliance.check_project_has_dispatch_routing(repo_root=tmp_path)
        assert issues == []

    def test_green_when_project_has_4a(self, tmp_path):
        _git_init(tmp_path)
        _commit_file(tmp_path, "projects/foo/PROJECT.md", _PROJECT_WITH_PHASES_AND_4A)
        issues = compliance.check_project_has_dispatch_routing(repo_root=tmp_path)
        assert issues == []

    def test_surfaces_when_phases_but_no_4a(self, tmp_path):
        _git_init(tmp_path)
        _commit_file(tmp_path, "projects/foo/PROJECT.md", _PROJECT_WITH_PHASES_NO_4A)
        issues = compliance.check_project_has_dispatch_routing(repo_root=tmp_path)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert issues[0]["symbol"] == "project-missing-dispatch-routing"
        assert "projects/foo/PROJECT.md" in issues[0]["file"]

    def test_silent_when_project_has_no_phases(self, tmp_path):
        _git_init(tmp_path)
        _commit_file(tmp_path, "projects/design-only/PROJECT.md", _PROJECT_NO_PHASES)
        issues = compliance.check_project_has_dispatch_routing(repo_root=tmp_path)
        assert issues == []

    def test_grandfathered_pre_birthday(self, tmp_path):
        _git_init(tmp_path)
        # Commit dated BEFORE 2026-05-26 birthday
        _commit_file(
            tmp_path, "projects/legacy/PROJECT.md", _PROJECT_WITH_PHASES_NO_4A,
            date_iso="2026-04-15T12:00:00",
        )
        issues = compliance.check_project_has_dispatch_routing(repo_root=tmp_path)
        # Grandfathered — pre-birthday projects skipped
        assert issues == []

    def test_not_grandfathered_post_birthday(self, tmp_path):
        _git_init(tmp_path)
        _commit_file(
            tmp_path, "projects/new/PROJECT.md", _PROJECT_WITH_PHASES_NO_4A,
            date_iso="2026-05-27T12:00:00",
        )
        issues = compliance.check_project_has_dispatch_routing(repo_root=tmp_path)
        assert len(issues) == 1
        assert "projects/new/PROJECT.md" in issues[0]["file"]

    def test_birthday_inclusive(self, tmp_path):
        # Project committed ON the birthday must carry §4a (boundary case)
        _git_init(tmp_path)
        _commit_file(
            tmp_path, "projects/birthday/PROJECT.md", _PROJECT_WITH_PHASES_NO_4A,
            date_iso="2026-05-26T12:00:00",
        )
        issues = compliance.check_project_has_dispatch_routing(repo_root=tmp_path)
        # Strict less-than means birthday-day itself is post-birthday → flagged
        assert len(issues) == 1

    def test_multi_location_resolution(self, tmp_path):
        """Walks all three valid locations: root, product, core."""
        _git_init(tmp_path)
        _commit_file(tmp_path, "projects/root-proj/PROJECT.md", _PROJECT_WITH_PHASES_NO_4A,
                     date_iso="2026-05-27T12:00:00")
        _commit_file(tmp_path, "products/erp/projects/erp-proj/PROJECT.md", _PROJECT_WITH_PHASES_NO_4A,
                     date_iso="2026-05-27T12:00:00")
        _commit_file(tmp_path, "core/projects/core-proj/PROJECT.md", _PROJECT_WITH_PHASES_NO_4A,
                     date_iso="2026-05-27T12:00:00")
        issues = compliance.check_project_has_dispatch_routing(repo_root=tmp_path)
        assert len(issues) == 3
        files = {i["file"] for i in issues}
        assert any("root-proj" in f for f in files)
        assert any("erp-proj" in f for f in files)
        assert any("core-proj" in f for f in files)

    def test_untracked_file_falls_through_to_flag(self, tmp_path):
        """Untracked PROJECT.md (no git history) is assumed NEW → flagged."""
        _git_init(tmp_path)
        # Write the file but do NOT commit
        fp = tmp_path / "projects" / "untracked" / "PROJECT.md"
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(_PROJECT_WITH_PHASES_NO_4A)
        issues = compliance.check_project_has_dispatch_routing(repo_root=tmp_path)
        # Untracked → assumed new → flagged (better to surface than silently grandfather)
        assert len(issues) == 1
        assert "projects/untracked/PROJECT.md" in issues[0]["file"]

    def test_section_4a_variant_headers(self, tmp_path):
        """Accept variants: `## 4a.` and `## 4a Dispatch routing`."""
        _git_init(tmp_path)
        variant = _PROJECT_WITH_PHASES_AND_4A.replace(
            "## 4a. Dispatch routing (REQUIRED — the slice-to-engineer map)",
            "## 4a Dispatch routing",
        )
        _commit_file(tmp_path, "projects/variant/PROJECT.md", variant,
                     date_iso="2026-05-27T12:00:00")
        issues = compliance.check_project_has_dispatch_routing(repo_root=tmp_path)
        assert issues == []
