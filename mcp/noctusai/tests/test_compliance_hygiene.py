"""Regression tests for the hygiene-compliance keeper detectors —
`keeper-housekeeping-upgrade` Phase 1.

Covers:
  - `check_archive_staleness`
  - `check_dispatcher_staleness`
  - `check_branch_orphan`
  - `check_gitignore_drift`

Each detector gets a focused TestCheck<...> class. Tests use the
`tmp_path` fixture for filesystem state; the branch-orphan suite
shells out to `git` against an init'd tmp repo (no monkey-patching
of our own code per the no-monkey-patch rule).
"""
import datetime as dt
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_archive_staleness,
    check_branch_orphan,
    check_dispatcher_staleness,
    check_gitignore_drift,
    check_new_script_lacks_mcp_analog,
)


# ---------------------------------------------------------------------------
# check_archive_staleness
# ---------------------------------------------------------------------------


class TestArchiveStaleness:
    """`archive/<bucket>/YYYY-MM-DD/` folders older than D-2 → warning/high."""

    def _mk_archive(self, tmp_path: Path, *dated_names: str, bucket: str = "projects") -> Path:
        """Create `<tmp_path>/archive/<bucket>/<name>/` for each `<name>`."""
        bucket_dir = tmp_path / "archive" / bucket
        bucket_dir.mkdir(parents=True)
        for name in dated_names:
            (bucket_dir / name).mkdir()
        return tmp_path

    def test_today_and_yesterday_pass(self, tmp_path):
        today = dt.date.today()
        yesterday = today - dt.timedelta(days=1)
        self._mk_archive(tmp_path, today.isoformat(), yesterday.isoformat())
        issues = check_archive_staleness(tmp_path)
        assert issues == [], f"today+yesterday must not flag, got: {issues}"

    def test_two_days_ago_is_stale_warning(self, tmp_path):
        old = dt.date.today() - dt.timedelta(days=2)
        self._mk_archive(tmp_path, old.isoformat())
        issues = check_archive_staleness(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "2 days old" in issues[0]["issue"]

    def test_past_seven_days_is_high(self, tmp_path):
        old = dt.date.today() - dt.timedelta(days=14)
        self._mk_archive(tmp_path, old.isoformat())
        issues = check_archive_staleness(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"
        assert "14 days old" in issues[0]["issue"]

    def test_non_date_folder_ignored(self, tmp_path):
        # README, "features", and other non-date-stamped buckets must not
        # be flagged (only YYYY-MM-DD-named folders qualify).
        self._mk_archive(tmp_path, "README.md", "not-a-date", bucket="seed-absorption")
        # The "README.md" .mkdir() created an actual dir (not a file) but
        # the name regex rejects it — that's the test point.
        issues = check_archive_staleness(tmp_path)
        assert issues == [], f"non-date names must not flag, got: {issues}"

    def test_missing_archive_dir_no_issues(self, tmp_path):
        # Fresh repo with no archive/ folder → silent pass.
        issues = check_archive_staleness(tmp_path)
        assert issues == []


# ---------------------------------------------------------------------------
# check_dispatcher_staleness
# ---------------------------------------------------------------------------


class TestDispatcherStaleness:
    """`.claude/dispatcher.md` `## Pending` entries older than 24h → flagged."""

    def _mk_inbox(self, tmp_path: Path, pending_block: str) -> Path:
        # Note: avoid textwrap.dedent here — the embedded pending_block
        # often has un-indented lines, breaking dedent's common-prefix
        # heuristic. Use a literal newline-separated body.
        content = (
            "# Dispatcher — two-session coordination\n"
            "\n"
            "## Pending\n"
            f"{pending_block}\n"
            "## Completed (last 24h)\n"
        )
        (tmp_path / ".claude").mkdir(exist_ok=True)
        (tmp_path / ".claude" / "dispatcher.md").write_text(content)
        return tmp_path

    def test_fresh_entry_does_not_flag(self, tmp_path):
        now = dt.datetime.now()
        ts = now.strftime("%Y-%m-%dT%H:%M")
        self._mk_inbox(tmp_path, f"\n### {ts} — FRESH-TASK\n- Type: dispatch\n")
        issues = check_dispatcher_staleness(tmp_path)
        assert issues == [], f"fresh entry must not flag, got: {issues}"

    def test_entry_25h_old_is_warning(self, tmp_path):
        old = dt.datetime.now() - dt.timedelta(hours=25)
        ts = old.strftime("%Y-%m-%dT%H:%M")
        self._mk_inbox(tmp_path, f"\n### {ts} — STALE-TASK\n- Type: dispatch\n")
        issues = check_dispatcher_staleness(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "STALE-TASK" in issues[0]["issue"]

    def test_entry_eight_days_old_is_high(self, tmp_path):
        old = dt.datetime.now() - dt.timedelta(days=8)
        ts = old.strftime("%Y-%m-%dT%H:%M")
        self._mk_inbox(tmp_path, f"\n### {ts} — ABANDONED\n")
        issues = check_dispatcher_staleness(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"

    def test_completed_entries_not_flagged(self, tmp_path):
        """Old entries inside `## Completed (last 24h)` must not flag — only
        `## Pending` is the active queue."""
        old = dt.datetime.now() - dt.timedelta(days=3)
        ts = old.strftime("%Y-%m-%dT%H:%M")
        content = (
            "# Dispatcher — two-session coordination\n"
            "\n"
            "## Pending\n"
            "\n"
            "## Completed (last 24h)\n"
            "\n"
            f"### {ts} — DONE-OLD ✅\n"
        )
        (tmp_path / ".claude").mkdir(exist_ok=True)
        (tmp_path / ".claude" / "dispatcher.md").write_text(content)
        issues = check_dispatcher_staleness(tmp_path)
        assert issues == [], f"completed entries must not flag, got: {issues}"

    def test_no_inbox_file_no_issues(self, tmp_path):
        # If `.claude/dispatcher.md` doesn't exist, the detector is silent
        # (not every checkout uses the two-session pattern).
        issues = check_dispatcher_staleness(tmp_path)
        assert issues == []


# ---------------------------------------------------------------------------
# check_branch_orphan
# ---------------------------------------------------------------------------


def _run(cwd: Path, *args: str) -> str:
    """Helper: run git in tmp repo, return stdout, raise on non-zero."""
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, check=True, timeout=15,
    ).stdout


class TestBranchOrphan:
    """Branches merged to `origin/main` AND >30d stale → warning."""

    def _init_repo_with_origin(self, tmp_path: Path) -> Path:
        """Initialize a git repo + a 'origin' bare clone so we have
        `origin/main` for the merged-check."""
        repo = tmp_path / "repo"
        origin = tmp_path / "origin.git"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, timeout=10)
        # Identity required for commits on systems without global config.
        _run(repo, "config", "user.email", "test@example.com")
        _run(repo, "config", "user.name", "Test")
        (repo / "README.md").write_text("hello\n")
        _run(repo, "add", "README.md")
        _run(repo, "commit", "-q", "-m", "initial")
        subprocess.run(
            ["git", "clone", "--bare", "-q", str(repo), str(origin)],
            check=True, timeout=10,
        )
        _run(repo, "remote", "add", "origin", str(origin))
        _run(repo, "fetch", "-q", "origin")
        return repo

    def test_no_branches_returns_empty(self, tmp_path):
        repo = self._init_repo_with_origin(tmp_path)
        issues = check_branch_orphan(repo)
        assert issues == []

    def test_fresh_merged_branch_does_not_flag(self, tmp_path):
        repo = self._init_repo_with_origin(tmp_path)
        # Create a merged branch with TODAY's commit date — fresh, must not flag.
        _run(repo, "checkout", "-q", "-b", "feature-fresh")
        (repo / "fresh.txt").write_text("x")
        _run(repo, "add", "fresh.txt")
        _run(repo, "commit", "-q", "-m", "fresh")
        _run(repo, "checkout", "-q", "main")
        _run(repo, "merge", "-q", "--no-ff", "-m", "merge fresh", "feature-fresh")
        # Push main forward so origin/main sees the merge → branch is "merged".
        _run(repo, "push", "-q", "origin", "main")
        _run(repo, "fetch", "-q", "origin")
        issues = check_branch_orphan(repo)
        assert issues == [], f"fresh merged branch must not flag, got: {issues}"

    def test_old_merged_branch_flags(self, tmp_path):
        repo = self._init_repo_with_origin(tmp_path)
        # Create a branch whose commit date is well past 30 days. Use
        # GIT_COMMITTER_DATE + GIT_AUTHOR_DATE env to backdate.
        _run(repo, "checkout", "-q", "-b", "feature-old")
        (repo / "old.txt").write_text("y")
        _run(repo, "add", "old.txt")
        env_date = "2025-01-01T12:00:00"
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-q", "-m", "old"],
            env={"GIT_COMMITTER_DATE": env_date, "GIT_AUTHOR_DATE": env_date, "PATH": __import__("os").environ.get("PATH", "")},
            check=True, timeout=10,
        )
        _run(repo, "checkout", "-q", "main")
        _run(repo, "merge", "-q", "--no-ff", "-m", "merge old", "feature-old")
        _run(repo, "push", "-q", "origin", "main")
        _run(repo, "fetch", "-q", "origin")
        issues = check_branch_orphan(repo)
        assert any(i["file"].endswith("feature-old") for i in issues), issues
        # All emitted should be warning by default (single orphan, <50 cap).
        assert all(i["severity"] == "warning" for i in issues)

    def test_unmerged_old_branch_not_flagged(self, tmp_path):
        repo = self._init_repo_with_origin(tmp_path)
        _run(repo, "checkout", "-q", "-b", "feature-unmerged")
        (repo / "wip.txt").write_text("z")
        _run(repo, "add", "wip.txt")
        env_date = "2025-01-01T12:00:00"
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-q", "-m", "wip"],
            env={"GIT_COMMITTER_DATE": env_date, "GIT_AUTHOR_DATE": env_date, "PATH": __import__("os").environ.get("PATH", "")},
            check=True, timeout=10,
        )
        # Do NOT merge; remain unmerged → must not flag even though old.
        _run(repo, "checkout", "-q", "main")
        issues = check_branch_orphan(repo)
        assert not any(i["file"].endswith("feature-unmerged") for i in issues), issues


# ---------------------------------------------------------------------------
# check_gitignore_drift
# ---------------------------------------------------------------------------


class TestGitignoreDrift:
    """`.gitignore` missing expected transient-coordination paths → warning."""

    def test_all_expected_present_no_issues(self, tmp_path):
        (tmp_path / ".gitignore").write_text(
            "node_modules/\n"
            ".claude/dispatcher.md\n"
            "scripts/mole-last-sweep.log\n"
            "scripts/archive-clean-last-sweep.log\n"
        )
        issues = check_gitignore_drift(tmp_path)
        assert issues == [], f"all expected present must not flag, got: {issues}"

    def test_all_expected_missing_flags_each(self, tmp_path):
        (tmp_path / ".gitignore").write_text("node_modules/\n")
        issues = check_gitignore_drift(tmp_path)
        # All 3 paths missing → 3 warnings.
        flagged = {i["issue"] for i in issues}
        assert len(issues) == 3, f"expected 3 missing entries, got {len(issues)}: {issues}"
        assert all(i["severity"] == "warning" for i in issues)
        assert any(".claude/dispatcher.md" in msg for msg in flagged)
        assert any("scripts/mole-last-sweep.log" in msg for msg in flagged)
        assert any("scripts/archive-clean-last-sweep.log" in msg for msg in flagged)

    def test_anchored_leading_slash_accepted(self, tmp_path):
        # `.gitignore` users sometimes anchor with `/path/...`; the detector
        # accepts both the bare form and the leading-slash form.
        (tmp_path / ".gitignore").write_text(
            "/.claude/dispatcher.md\n"
            "/scripts/mole-last-sweep.log\n"
            "/scripts/archive-clean-last-sweep.log\n"
        )
        issues = check_gitignore_drift(tmp_path)
        assert issues == [], f"anchored form must be accepted, got: {issues}"

    def test_no_gitignore_at_all_high_severity(self, tmp_path):
        issues = check_gitignore_drift(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"
        assert "no `.gitignore`" in issues[0]["issue"]

    def test_comments_and_blanks_ignored(self, tmp_path):
        (tmp_path / ".gitignore").write_text(
            "# Comment\n"
            "\n"
            ".claude/dispatcher.md\n"
            "  # whitespace-prefixed comment is also ignored after .strip()\n"
            "scripts/mole-last-sweep.log\n"
            "scripts/archive-clean-last-sweep.log\n"
        )
        issues = check_gitignore_drift(tmp_path)
        # The whitespace-prefixed line starts with "#" after strip, so it's
        # treated as a comment — all 3 expected paths present → no issues.
        assert issues == [], f"comments must be ignored, got: {issues}"


# ---------------------------------------------------------------------------
# check_new_script_lacks_mcp_analog
# ---------------------------------------------------------------------------

_DOC_REL = "KNOWLEDGE-BASE/CONTEXT/PATTERNS/architect/mcp-first-scripts.md"


class TestNewScriptLacksMcpAnalog:
    """Every top-level `scripts/*.{sh,py}` MUST have a §3 manifest row;
    an undecided one → `warning`."""

    def _setup(self, tmp_path: Path, *, manifest_names, disk_names, doc=True):
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        for name in disk_names:
            (scripts / name).write_text("#!/bin/sh\n")
        if doc:
            doc_path = tmp_path / _DOC_REL
            doc_path.parent.mkdir(parents=True)
            rows = "\n".join(f"| `{n}` | C | → tool |" for n in manifest_names)
            doc_path.write_text(
                "# MCP-first scripts\n\n"
                "## 1. The rule\n\n`scripts/foo.sh` is an example in prose.\n\n"
                "## 3. Classification manifest\n\n"
                "| script | bucket | disposition |\n|---|---|---|\n"
                f"{rows}\n\n"
                "## 4. Companion rules\n\n| `unrelated.sh` | x | y |\n"
            )
        return tmp_path

    def test_classified_script_does_not_flag(self, tmp_path):
        self._setup(tmp_path, manifest_names=["a.sh", "b.py"],
                    disk_names=["a.sh", "b.py"])
        assert check_new_script_lacks_mcp_analog(tmp_path) == []

    def test_unclassified_script_flags_warning(self, tmp_path):
        self._setup(tmp_path, manifest_names=["a.sh"],
                    disk_names=["a.sh", "rogue.sh"])
        issues = check_new_script_lacks_mcp_analog(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert issues[0]["file"] == "scripts/rogue.sh"

    def test_only_section_3_widens_allowset(self, tmp_path):
        # `unrelated.sh` is backticked in §4, NOT §3 — must still flag.
        self._setup(tmp_path, manifest_names=["a.sh"],
                    disk_names=["a.sh", "unrelated.sh"])
        issues = check_new_script_lacks_mcp_analog(tmp_path)
        assert [i["file"] for i in issues] == ["scripts/unrelated.sh"], issues

    def test_non_script_entries_ignored(self, tmp_path):
        tp = self._setup(tmp_path, manifest_names=["a.sh"], disk_names=["a.sh"])
        (tp / "scripts" / "pre-commit").write_text("#!/bin/sh\n")  # extensionless
        (tp / "scripts" / "README.md").write_text("# readme\n")
        (tp / "scripts" / "x.log").write_text("log\n")
        assert check_new_script_lacks_mcp_analog(tp) == []

    def test_missing_doc_no_issues(self, tmp_path):
        # Worktree off an older base (rule not yet codified) → graceful.
        self._setup(tmp_path, manifest_names=[], disk_names=["a.sh"],
                    doc=False)
        assert check_new_script_lacks_mcp_analog(tmp_path) == []

    def test_recurses_subfolders_basename_match(self, tmp_path):
        # Phase-6 intent-folders: a script moved into scripts/bootstrap/
        # is still enforced (rglob); manifest is basename-keyed so the row
        # is path-stable across the move. An unrowed subdir script flags.
        tp = self._setup(tmp_path, manifest_names=["setup.sh"],
                          disk_names=[])
        (tp / "scripts" / "bootstrap").mkdir()
        (tp / "scripts" / "bootstrap" / "setup.sh").write_text("#!/bin/sh\n")
        (tp / "scripts" / "infra").mkdir()
        (tp / "scripts" / "infra" / "rogue.sh").write_text("#!/bin/sh\n")
        # codemods/ stays out of scope even recursively.
        (tp / "scripts" / "codemods").mkdir()
        (tp / "scripts" / "codemods" / "x.py").write_text("y=1\n")
        issues = check_new_script_lacks_mcp_analog(tp)
        names = sorted(i["file"] for i in issues)
        assert names == ["scripts/rogue.sh"], names  # basename, not codemods

    def test_real_tree_baseline_zero(self):
        """The live repo tree must be clean — the recursive keeper +
        basename-keyed manifest stay green after the Phase-6 folder move
        (scripts/{hooks,bootstrap,infra}/)."""
        assert check_new_script_lacks_mcp_analog() == []

    def test_real_tree_baseline_zero(self):
        """The live repo tree must be clean (Phase 1 seeded the manifest
        with all 25 current scripts)."""
        assert check_new_script_lacks_mcp_analog() == []
