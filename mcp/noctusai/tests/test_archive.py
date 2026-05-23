"""Tests for the archive MCP tool."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.archive import (
    archive,
    archive_clean,
    _derive_default_summary,
    _detect_mode,
    _next_nn,
    _today_str,
    _yesterday_str,
)


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a tmp git repo with the structure the archive tool expects."""
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(tmp_path), check=True)
    # Pre-create archive/ structure
    (tmp_path / "archive" / "projects").mkdir(parents=True)
    (tmp_path / "archive" / "features").mkdir(parents=True)
    (tmp_path / "archive" / "projects" / ".gitkeep").touch()
    (tmp_path / "archive" / "features" / ".gitkeep").touch()
    # Pre-create projects/ + features/ folders
    (tmp_path / "projects").mkdir()
    (tmp_path / "features").mkdir()
    # Initial commit so git mv works
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(tmp_path), check=True)
    return tmp_path


def _make_project(repo: Path, slug: str) -> Path:
    """Create a project folder + PROJECT.md + commit it."""
    proj = repo / "projects" / slug
    proj.mkdir()
    (proj / "PROJECT.md").write_text(f"# {slug}\n\nfake project.\n")
    (proj / "proposals").mkdir()
    (proj / "proposals" / ".gitkeep").touch()
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"file {slug}"], cwd=str(repo), check=True)
    return proj


def _make_feature(repo: Path, slug: str) -> Path:
    """Create a feature .md + commit it."""
    feat = repo / "features" / f"{slug}.md"
    feat.write_text(f"# {slug}\n\nfake feature.\n")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"file {slug}"], cwd=str(repo), check=True)
    return feat


# ---------------------------------------------------------------------------
# Mode auto-detection
# ---------------------------------------------------------------------------

class TestDetectMode:
    def test_project_md_file_detected_as_project(self, tmp_repo):
        proj = _make_project(tmp_repo, "foo")
        assert _detect_mode(proj / "PROJECT.md") == "project"

    def test_directory_with_project_md_detected_as_project(self, tmp_repo):
        proj = _make_project(tmp_repo, "foo")
        assert _detect_mode(proj) == "project"

    def test_feature_md_under_features_detected_as_feature(self, tmp_repo):
        feat = _make_feature(tmp_repo, "foo")
        assert _detect_mode(feat) == "feature"

    def test_arbitrary_md_not_under_features_is_ad_hoc(self, tmp_repo):
        other = tmp_repo / "OTHER.md"
        other.write_text("not a feature")
        assert _detect_mode(other) == "ad_hoc"

    def test_arbitrary_directory_is_ad_hoc(self, tmp_repo):
        d = tmp_repo / "scratch"
        d.mkdir()
        assert _detect_mode(d) == "ad_hoc"


# ---------------------------------------------------------------------------
# NN computation
# ---------------------------------------------------------------------------

class TestNextNN:
    def test_empty_returns_1(self, tmp_path):
        assert _next_nn(tmp_path) == 1

    def test_nonexistent_returns_1(self, tmp_path):
        assert _next_nn(tmp_path / "does-not-exist") == 1

    def test_one_existing_returns_2(self, tmp_path):
        (tmp_path / "01-foo").mkdir()
        assert _next_nn(tmp_path) == 2

    def test_multiple_returns_max_plus_1(self, tmp_path):
        (tmp_path / "01-foo").mkdir()
        (tmp_path / "02-bar").mkdir()
        (tmp_path / "03-baz").mkdir()
        assert _next_nn(tmp_path) == 4

    def test_skips_non_numbered_entries(self, tmp_path):
        (tmp_path / ".gitkeep").touch()
        (tmp_path / "01-foo").mkdir()
        (tmp_path / "README.md").touch()
        assert _next_nn(tmp_path) == 2

    def test_handles_gaps(self, tmp_path):
        (tmp_path / "01-foo").mkdir()
        (tmp_path / "05-bar").mkdir()  # gap
        assert _next_nn(tmp_path) == 6


# ---------------------------------------------------------------------------
# Project archive
# ---------------------------------------------------------------------------

class TestArchiveProject:
    def test_basic_project_archive(self, tmp_repo):
        proj = _make_project(tmp_repo, "alpha")
        result = archive("projects/alpha", repo_root=tmp_repo)
        assert result["mode"] == "project"
        assert result["next_NN"] == 1
        today = _today_str()
        assert result["archived_to"] == f"archive/projects/{today}/01-alpha"
        # Source removed
        assert not proj.exists()
        # Destination exists with content
        dst = tmp_repo / "archive" / "projects" / today / "01-alpha"
        assert dst.exists()
        assert (dst / "PROJECT.md").exists()
        assert (dst / "proposals").exists()

    def test_second_project_same_day_gets_NN_02(self, tmp_repo):
        _make_project(tmp_repo, "alpha")
        archive("projects/alpha", repo_root=tmp_repo)
        # Commit the move so the next archive starts from clean state
        subprocess.run(["git", "commit", "-q", "-am", "archive alpha"], cwd=str(tmp_repo), check=True)
        _make_project(tmp_repo, "beta")
        result = archive("projects/beta", repo_root=tmp_repo)
        assert result["next_NN"] == 2
        today = _today_str()
        assert result["archived_to"] == f"archive/projects/{today}/02-beta"

    def test_auto_detect_project_from_directory(self, tmp_repo):
        _make_project(tmp_repo, "gamma")
        result = archive("projects/gamma", repo_root=tmp_repo)  # no mode specified
        assert result["mode"] == "project"

    def test_explicit_project_md_path_works(self, tmp_repo):
        _make_project(tmp_repo, "delta")
        result = archive("projects/delta/PROJECT.md", repo_root=tmp_repo)
        assert result["mode"] == "project"
        # Slug is derived from parent folder name
        today = _today_str()
        assert "01-delta" in result["archived_to"]


# ---------------------------------------------------------------------------
# Feature archive
# ---------------------------------------------------------------------------

class TestArchiveFeature:
    def test_basic_feature_archive(self, tmp_repo):
        feat = _make_feature(tmp_repo, "easy-fix")
        result = archive("features/easy-fix.md", repo_root=tmp_repo)
        assert result["mode"] == "feature"
        assert result["next_NN"] == 1
        today = _today_str()
        assert result["archived_to"] == f"archive/features/{today}/01-easy-fix.md"
        assert not feat.exists()
        dst = tmp_repo / "archive" / "features" / today / "01-easy-fix.md"
        assert dst.exists()
        assert "easy-fix" in dst.read_text()

    def test_second_feature_same_day_gets_NN_02(self, tmp_repo):
        _make_feature(tmp_repo, "first")
        archive("features/first.md", repo_root=tmp_repo)
        subprocess.run(["git", "commit", "-q", "-am", "archive first"], cwd=str(tmp_repo), check=True)
        _make_feature(tmp_repo, "second")
        result = archive("features/second.md", repo_root=tmp_repo)
        assert result["next_NN"] == 2

    def test_auto_detect_feature(self, tmp_repo):
        _make_feature(tmp_repo, "auto")
        result = archive("features/auto.md", repo_root=tmp_repo)  # no mode
        assert result["mode"] == "feature"


# ---------------------------------------------------------------------------
# Ad-hoc archive
# ---------------------------------------------------------------------------

class TestArchiveAdHoc:
    def test_ad_hoc_requires_name(self, tmp_repo):
        scratch = tmp_repo / "scratch"
        scratch.mkdir()
        (scratch / "stuff.txt").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "scratch"], cwd=str(tmp_repo), check=True)
        with pytest.raises(ValueError, match="name is required"):
            archive("scratch", mode="ad_hoc", repo_root=tmp_repo)

    def test_ad_hoc_basic(self, tmp_repo):
        scratch = tmp_repo / "scratch"
        scratch.mkdir()
        (scratch / "stuff.txt").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "scratch"], cwd=str(tmp_repo), check=True)
        result = archive("scratch", mode="ad_hoc", name="my-scratch", repo_root=tmp_repo)
        assert result["mode"] == "ad_hoc"
        assert result["next_NN"] is None
        # Path matches archive/<YYYY-MM-DD>_<HH-MM-SS>_my-scratch
        assert result["archived_to"].startswith("archive/")
        assert result["archived_to"].endswith("_my-scratch")
        assert not scratch.exists()


# ---------------------------------------------------------------------------
# Idempotency guard
# ---------------------------------------------------------------------------

class TestIdempotencyGuard:
    def test_refuses_already_archived_path(self, tmp_repo):
        # Pre-create an archived project
        today = _today_str()
        archived = tmp_repo / "archive" / "projects" / today / "01-already"
        archived.mkdir(parents=True)
        (archived / "PROJECT.md").write_text("already archived")
        with pytest.raises(ValueError, match="already under archive"):
            archive(str(archived), repo_root=tmp_repo)

    def test_refuses_archive_root_itself(self, tmp_repo):
        with pytest.raises(ValueError, match="already under archive"):
            archive("archive", repo_root=tmp_repo)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrors:
    def test_nonexistent_target_raises(self, tmp_repo):
        with pytest.raises(ValueError, match="does not exist"):
            archive("projects/never-existed", repo_root=tmp_repo)

    def test_invalid_mode_raises(self, tmp_repo):
        _make_project(tmp_repo, "x")
        with pytest.raises(ValueError, match="invalid mode"):
            archive("projects/x", mode="not-a-mode", repo_root=tmp_repo)


# ---------------------------------------------------------------------------
# Git history preservation
# ---------------------------------------------------------------------------

class TestHistoryPreservation:
    def test_git_log_follow_works_after_archive(self, tmp_repo):
        proj = _make_project(tmp_repo, "histtest")
        # Commit a change to PROJECT.md so there's history to follow
        (proj / "PROJECT.md").write_text("# histtest\n\nupdated content.\n")
        subprocess.run(["git", "commit", "-q", "-am", "update histtest"], cwd=str(tmp_repo), check=True)
        # Archive
        result = archive("projects/histtest", repo_root=tmp_repo)
        # Commit the move
        subprocess.run(["git", "commit", "-q", "-m", "archive histtest"], cwd=str(tmp_repo), check=True)
        # git log --follow should walk back through the project's pre-archive history
        archived_md = result["archived_to"] + "/PROJECT.md"
        out = subprocess.run(
            ["git", "log", "--follow", "--oneline", "--", archived_md],
            cwd=str(tmp_repo),
            capture_output=True,
            text=True,
            check=True,
        )
        # Should have at least 3 commits in history: file, update, archive-move
        assert len(out.stdout.strip().splitlines()) >= 3


# ---------------------------------------------------------------------------
# MCP tool registration
# ---------------------------------------------------------------------------

class TestMcpRegistration:
    def test_register_function_exists(self):
        from tools.noctus.dev.archive import register
        assert callable(register)

    def test_archive_tool_in_server_registry(self):
        from server import build_server
        s = build_server()
        manager = s._tool_manager
        assert "noctus.dev.archive" in manager._tools


# ---------------------------------------------------------------------------
# worktree_path — caller-aware path resolution.
# ---------------------------------------------------------------------------


class TestWorktreeAwarePathResolution:
    """`archive` honors `worktree_path` — files archive into the caller's
    worktree, not the MCP server's startup workspace.

    Filed by ``projects/mcp-worktree-path-resolution/``.
    """

    def _make_fake_worktree_repo(self, tmp_path: Path) -> Path:
        """Build a worktree-shaped repo: real git init + .noctusai-workspace
        marker. Real git is required because archive() runs `git mv`.
        """
        wt = tmp_path / "wt"
        wt.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(wt), check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(wt), check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=str(wt), check=True)
        (wt / ".noctusai-workspace").write_text(
            "workspace_kind=primary\nworkspace_name=wt\n", encoding="utf-8",
        )
        (wt / "archive" / "projects").mkdir(parents=True)
        (wt / "archive" / "features").mkdir(parents=True)
        (wt / "archive" / "projects" / ".gitkeep").touch()
        (wt / "archive" / "features" / ".gitkeep").touch()
        (wt / "projects").mkdir()
        subprocess.run(["git", "add", "-A"], cwd=str(wt), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(wt), check=True)
        return wt

    def test_archive_lands_in_worktree(self, tmp_path):
        wt = self._make_fake_worktree_repo(tmp_path)
        # Plant a project inside the worktree.
        proj = wt / "projects" / "demo"
        proj.mkdir()
        (proj / "PROJECT.md").write_text("# demo\n")
        subprocess.run(["git", "add", "-A"], cwd=str(wt), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "demo"], cwd=str(wt), check=True)

        result = archive(
            target_path=str(proj),
            mode="project",
            worktree_path=wt,
        )
        # archived_to is relative to the worktree root.
        archived = wt / result["archived_to"]
        assert archived.exists(), (
            f"archive with worktree_path={wt} must land at {archived}, "
            f"got result={result}"
        )

    def test_invalid_worktree_path_raises(self, tmp_path):
        bad = tmp_path / "not-wt"
        bad.mkdir()
        with pytest.raises(ValueError):
            archive(
                target_path=str(bad),
                mode="ad_hoc",
                name="x",
                worktree_path=bad,
            )

    def test_explicit_repo_root_overrides_worktree_path(self, tmp_path):
        """`repo_root` (test seam) wins over `worktree_path`."""
        wt = self._make_fake_worktree_repo(tmp_path)
        # Build a second repo as the "sink"; archive must land here, not wt.
        sink = tmp_path / "sink"
        sink.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(sink), check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=str(sink), check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=str(sink), check=True)
        (sink / "archive" / "projects").mkdir(parents=True)
        (sink / "projects").mkdir()
        proj = sink / "projects" / "demo"
        proj.mkdir()
        (proj / "PROJECT.md").write_text("# demo\n")
        subprocess.run(["git", "add", "-A"], cwd=str(sink), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(sink), check=True)

        result = archive(
            target_path=str(proj),
            mode="project",
            repo_root=sink,  # should win
            worktree_path=wt,
        )
        archived = sink / result["archived_to"]
        assert archived.exists()


# ---------------------------------------------------------------------------
# Phase 2 — ledger-stamp side-effect (project archives only).
# ---------------------------------------------------------------------------


class TestLedgerStampOnProjectArchive:
    """`archive(mode="project")` stamps a `project-history/ledger.ndjson`
    line BEFORE the git mv lands. Default-on; opt-out via
    ``skip_history=True``. Errors propagate.

    Filed per ``projects/project-history-ledger/PROJECT.md § 6 Phase 2``.
    """

    def test_project_archive_appends_one_ndjson_line(self, tmp_repo):
        """Sample project archive → ledger.ndjson grows by exactly one
        line; that line is valid JSON; ``slug`` matches the archived
        project.
        """
        proj = _make_project(tmp_repo, "phase2-sample")
        # Ledger doesn't exist yet — the tool should create it.
        ledger = tmp_repo / "project-history" / "ledger.ndjson"
        assert not ledger.exists()

        result = archive("projects/phase2-sample", repo_root=tmp_repo)

        # Ledger exists; exactly one line; that line is valid JSON for
        # this slug.
        assert ledger.exists(), "archive must create ledger.ndjson on first project stamp"
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1, f"expected exactly 1 ledger line; got {len(lines)}"
        rec = json.loads(lines[0])
        assert rec["slug"] == "phase2-sample"
        assert rec["status_at_close"] == "shipped"
        assert "short_summary" in rec
        assert "token_count" in rec
        # And the surfacing in archive's return dict:
        assert result["history"] is not None
        assert result["history"]["line_count"] == 1
        # Source still archived:
        assert not proj.exists()

    def test_second_project_archive_appends_second_line(self, tmp_repo):
        """Re-running on a second project appends (not overwrites)."""
        _make_project(tmp_repo, "first")
        archive("projects/first", repo_root=tmp_repo)
        subprocess.run(["git", "commit", "-q", "-am", "archive first"], cwd=str(tmp_repo), check=True)
        _make_project(tmp_repo, "second")
        archive("projects/second", repo_root=tmp_repo)

        ledger = tmp_repo / "project-history" / "ledger.ndjson"
        lines = ledger.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        slugs = [json.loads(L)["slug"] for L in lines]
        assert slugs == ["first", "second"]

    def test_skip_history_flag_disables_stamp(self, tmp_repo):
        """``skip_history=True`` — no ledger writes; archive still works."""
        _make_project(tmp_repo, "no-stamp")
        result = archive(
            "projects/no-stamp", repo_root=tmp_repo, skip_history=True
        )
        ledger = tmp_repo / "project-history" / "ledger.ndjson"
        assert not ledger.exists(), "skip_history=True must NOT create the ledger"
        assert result["history"] is None
        # But the archive itself still happened:
        assert result["mode"] == "project"
        today = _today_str()
        assert (tmp_repo / "archive" / "projects" / today / "01-no-stamp").exists()

    def test_feature_archive_does_not_stamp(self, tmp_repo):
        """Feature archives are NOT projects — no ledger entry."""
        _make_feature(tmp_repo, "feat")
        result = archive("features/feat.md", repo_root=tmp_repo)
        ledger = tmp_repo / "project-history" / "ledger.ndjson"
        assert not ledger.exists(), "feature archives must not stamp the ledger"
        assert result["history"] is None

    def test_ad_hoc_archive_does_not_stamp(self, tmp_repo):
        """Ad-hoc archives are NOT projects — no ledger entry."""
        scratch = tmp_repo / "scratch"
        scratch.mkdir()
        (scratch / "stuff.txt").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "scratch"], cwd=str(tmp_repo), check=True)
        result = archive(
            "scratch", mode="ad_hoc", name="ad-hoc-thing", repo_root=tmp_repo
        )
        ledger = tmp_repo / "project-history" / "ledger.ndjson"
        assert not ledger.exists()
        assert result["history"] is None

    def test_stamp_failure_aborts_archive_no_git_mv(self, tmp_repo):
        """If the ledger stamp raises, the archive must NOT proceed.

        We trigger a real failure by passing an invalid
        ``status_at_close`` — ``history_record`` raises ``ValueError``
        at the validation gate (real error path, NOT a monkey-patched
        mock — see the no-monkey-patching-of-our-own-code rule). The
        source project must remain in place; no archive folder gets
        created.

        Per the no-silent-errors rule: history_record errors propagate;
        archive does not swallow them.
        """
        proj = _make_project(tmp_repo, "fail-stamp")

        with pytest.raises(ValueError, match="invalid status_at_close"):
            archive(
                "projects/fail-stamp",
                repo_root=tmp_repo,
                status_at_close="not-a-valid-status",
            )

        # Source untouched — archive did NOT proceed:
        assert proj.exists(), "archive must NOT git-mv when ledger stamp fails"
        today = _today_str()
        archived_dst = tmp_repo / "archive" / "projects" / today / "01-fail-stamp"
        assert not archived_dst.exists(), "no archive folder when stamp aborts"
        # No ledger line written either (validation fails before append).
        ledger = tmp_repo / "project-history" / "ledger.ndjson"
        assert not ledger.exists() or ledger.read_text() == ""

    def test_explicit_summary_and_review_passed_through(self, tmp_repo):
        """Explicit summary_md / review_md / outcome_signals reach the
        ledger record."""
        _make_project(tmp_repo, "explicit")
        archive(
            "projects/explicit",
            repo_root=tmp_repo,
            summary_md="A precise human-written summary.",
            review_md="- step a\n- step b",
            outcome_signals=["pytest 60/60 green"],
        )
        ledger = tmp_repo / "project-history" / "ledger.ndjson"
        rec = json.loads(ledger.read_text().splitlines()[0])
        assert rec["short_summary"] == "A precise human-written summary."
        assert "step a" in rec["short_review"]
        assert rec["outcome_signals"] == ["pytest 60/60 green"]

    def test_default_status_is_shipped(self, tmp_repo):
        """When ``status_at_close`` is not supplied, default is
        ``shipped`` (archive's most common trigger)."""
        _make_project(tmp_repo, "defaults")
        archive("projects/defaults", repo_root=tmp_repo)
        ledger = tmp_repo / "project-history" / "ledger.ndjson"
        rec = json.loads(ledger.read_text().splitlines()[0])
        assert rec["status_at_close"] == "shipped"

    def test_explicit_status_passed_through(self, tmp_repo):
        """When ``status_at_close`` is supplied, it lands in the record."""
        _make_project(tmp_repo, "abandoned-one")
        archive(
            "projects/abandoned-one",
            repo_root=tmp_repo,
            status_at_close="abandoned",
        )
        ledger = tmp_repo / "project-history" / "ledger.ndjson"
        rec = json.loads(ledger.read_text().splitlines()[0])
        assert rec["status_at_close"] == "abandoned"


class TestDeriveDefaultSummary:
    """Default summary derivation when caller doesn't pass ``summary_md``."""

    def test_skips_headings(self):
        body = "# Title\n\nReal first sentence.\n"
        assert _derive_default_summary(body) == "Real first sentence."

    def test_skips_blockquotes(self):
        body = "# Title\n\n> a note\n\nThe meat.\n"
        assert _derive_default_summary(body) == "The meat."

    def test_strips_bullet_prefix(self):
        body = "# Title\n\n- bullet line one\n"
        assert _derive_default_summary(body) == "bullet line one"

    def test_falls_back_when_empty(self):
        assert _derive_default_summary("# only-headings\n\n# more\n") == "(no summary available)"
        assert _derive_default_summary("") == "(no summary available)"


# ---------------------------------------------------------------------------
# archive_clean — keep today+yesterday, classify D-2+ as stale.
# Behaviour-preserving port of scripts/archive-clean.sh.
# ---------------------------------------------------------------------------


def _make_archive_date_dir(repo: Path, date: str) -> Path:
    """Create archive/projects/<date>/ with a tracked file + commit."""
    d = repo / "archive" / "projects" / date
    d.mkdir(parents=True)
    (d / "01-proj" ).mkdir()
    (d / "01-proj" / "PROJECT.md").write_text(f"# proj {date}\n")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"archive {date}"], cwd=str(repo), check=True)
    return d


class TestArchiveCleanClassification:
    def test_no_archive_projects_dir_is_nothing(self, tmp_path):
        subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
        result = archive_clean(repo_root=tmp_path)
        assert result["status"] == "nothing"
        assert result["stale"] == []
        assert result["dry_run"] is True

    def test_today_and_yesterday_are_kept(self, tmp_repo):
        today = _today_str()
        yesterday = _yesterday_str()
        _make_archive_date_dir(tmp_repo, today)
        _make_archive_date_dir(tmp_repo, yesterday)
        result = archive_clean(repo_root=tmp_repo)
        assert set(result["kept"]) == {today, yesterday}
        assert result["stale"] == []
        assert result["status"] == "nothing"

    def test_old_date_is_stale(self, tmp_repo):
        today = _today_str()
        _make_archive_date_dir(tmp_repo, today)
        _make_archive_date_dir(tmp_repo, "2020-01-01")
        result = archive_clean(repo_root=tmp_repo)
        assert today in result["kept"]
        assert result["stale"] == ["archive/projects/2020-01-01"]
        assert result["status"] == "dry_run"

    def test_non_date_entries_skipped(self, tmp_repo):
        (tmp_repo / "archive" / "projects" / "README.md").write_text("not a date")
        (tmp_repo / "archive" / "projects" / "weird-folder").mkdir()
        subprocess.run(["git", "add", "-A"], cwd=str(tmp_repo), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "noise"], cwd=str(tmp_repo), check=True)
        result = archive_clean(repo_root=tmp_repo)
        assert "README.md" in result["skipped"]
        assert "weird-folder" in result["skipped"]
        assert result["stale"] == []


class TestArchiveCleanDryRunVsForce:
    def test_dry_run_default_removes_nothing(self, tmp_repo):
        _make_archive_date_dir(tmp_repo, _today_str())
        old = _make_archive_date_dir(tmp_repo, "2019-06-15")
        result = archive_clean(repo_root=tmp_repo)  # force defaults False
        assert result["dry_run"] is True
        assert result["removed"] == 0
        assert old.exists(), "dry-run must NOT remove the stale folder"

    def test_force_removes_stale_via_git_rm(self, tmp_repo):
        _make_archive_date_dir(tmp_repo, _today_str())
        old = _make_archive_date_dir(tmp_repo, "2019-06-15")
        old2 = _make_archive_date_dir(tmp_repo, "2018-03-03")
        result = archive_clean(repo_root=tmp_repo, force=True)
        assert result["status"] == "removed"
        assert result["removed"] == 2
        assert not old.exists()
        assert not old2.exists()

    def test_force_preserves_keep_window(self, tmp_repo):
        today = _today_str()
        keep = _make_archive_date_dir(tmp_repo, today)
        _make_archive_date_dir(tmp_repo, "2017-01-01")
        archive_clean(repo_root=tmp_repo, force=True)
        assert keep.exists(), "today's folder must survive a forced clean"

    def test_force_with_no_stale_is_nothing(self, tmp_repo):
        _make_archive_date_dir(tmp_repo, _today_str())
        result = archive_clean(repo_root=tmp_repo, force=True)
        assert result["status"] == "nothing"
        assert result["removed"] == 0


class TestArchiveCleanMcpRegistration:
    def test_archive_clean_tool_in_server_registry(self):
        from server import build_server
        s = build_server()
        assert "noctus.dev.archive_clean" in s._tool_manager._tools


class TestLearnBeforeArchiveGate:
    """archive() refuses to archive a PROJECT until learnings_absorbed=True —
    the lesson must outlive the folder (KB § "Durable docs are self-contained")."""

    def test_project_refuses_without_learnings_absorbed(self, tmp_repo):
        proj = _make_project(tmp_repo, "demo-proj")
        (proj / "findings.md").write_text("# findings\n- a lesson\n")
        with pytest.raises(ValueError, match="learn-before-archive"):
            archive(str(proj), repo_root=tmp_repo, skip_history=True)
        assert proj.exists(), "project must NOT be moved when the gate refuses"

    def test_project_proceeds_with_learnings_absorbed(self, tmp_repo):
        proj = _make_project(tmp_repo, "demo-proj2")
        (proj / "findings.md").write_text("# findings\n- a lesson\n")  # gate WOULD fire
        result = archive(
            str(proj), repo_root=tmp_repo, skip_history=True,
            learnings_absorbed=True,  # ...the flag bypasses it
        )
        assert result["mode"] == "project"
        assert result["archived_to"].startswith("archive/projects/")
        assert not proj.exists()

    def test_feature_mode_unaffected_by_gate(self, tmp_repo):
        feat = _make_feature(tmp_repo, "demo-feat")
        result = archive(str(feat), repo_root=tmp_repo, skip_history=True)
        assert result["mode"] == "feature"
