"""Merge-loss detector (noctus.dev.merge_loss_check): red + green fixtures on REAL git merges.

The incident class: a merge result silently lacks a line one side added (2026-11-10,
dev's `agent-creator` row vanished from 06-AGENTS.md with no markers). Every test builds a
throwaway repo and a real merge, so what is judged is git's own parents/base/index.
KB § PATTERNS/common/auto-generated-merge-drivers.md § Merge-loss detector.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.noctus.dev import merge_loss  # noqa: E402
from tools.noctus.dev.merge_loss import merge_loss_check  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
BASE = "".join(f"line-{i}\n" for i in range(1, 11))


def _git(root: Path, *a: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=root,
                          check=check, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "r"
    root.mkdir()
    (root / ".noctusai-workspace").write_text("")
    _git(root, "init", "-q", "-b", "main")
    (root / "doc.md").write_text(BASE)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def _branches(root: Path, ours: str, theirs: str, path: str = "doc.md") -> None:
    _git(root, "checkout", "-q", "-b", "theirs", "main")
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(theirs)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "theirs")
    _git(root, "checkout", "-q", "main")
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(ours)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "ours")


def _merge_with_result(root: Path, result: str, path: str = "doc.md") -> str:
    """A real merge commit whose tree holds `result` for `path` (simulates any driver/hand resolution)."""
    _git(root, "merge", "--no-commit", "--no-ff", "theirs", check=False)
    (root / path).write_text(result)
    _git(root, "add", path)
    _git(root, "commit", "-qm", "merge")
    return _git(root, "rev-parse", "HEAD").stdout.strip()


OURS_ADD = BASE.replace("line-2\n", "line-2\nOURS-NEW\n")
THEIRS_ADD = BASE.replace("line-8\n", "line-8\nTHEIRS-NEW\n")
BOTH = BASE.replace("line-2\n", "line-2\nOURS-NEW\n").replace("line-8\n", "line-8\nTHEIRS-NEW\n")


def _check(root: Path, **kw) -> dict:
    return merge_loss_check(worktree_path=root, log=False, **kw)


class TestDetectsLoss:
    def test_other_sides_added_line_dropped_is_reported(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD)
        sha = _merge_with_result(repo, OURS_ADD)          # the incident: "ours" alone
        r = _check(repo, merge_sha=sha)
        assert r["verdict"] == "dropped" and r["ok"] is False
        assert [(d["path"], d["side"], d["line"]) for d in r["dropped"]] == [("doc.md", "theirs", "THEIRS-NEW")]
        assert r["dropped"][0]["base_region"] and r["checked_files"] == 1

    def test_both_sides_kept_is_clean(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD)
        r = _check(repo, merge_sha=_merge_with_result(repo, BOTH))
        assert r["verdict"] == "clean" and r["ok"] is True and r["dropped"] == []

    def test_real_git_merge_is_clean(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD)
        _git(repo, "merge", "--no-edit", "theirs")
        r = _check(repo, merge_sha="HEAD")
        assert r["verdict"] == "clean" and r["checked_files"] == 1

    def test_ours_line_dropped_is_reported_too(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD)
        r = _check(repo, merge_sha=_merge_with_result(repo, THEIRS_ADD))
        assert [(d["side"], d["line"]) for d in r["dropped"]] == [("ours", "OURS-NEW")]

    def test_file_absent_from_result_is_reported(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD)
        _git(repo, "merge", "--no-commit", "--no-ff", "theirs", check=False)
        _git(repo, "rm", "-qf", "doc.md")
        _git(repo, "commit", "-qm", "merge")
        r = _check(repo, merge_sha="HEAD")
        assert r["verdict"] == "dropped" and "absent" in r["dropped"][0]["line"]


class TestExemptions:
    def test_both_sides_rewrote_the_same_line_either_resolution_is_fine(self, repo):
        ours = BASE.replace("line-5\n", "line-5 OURS\n")
        theirs = BASE.replace("line-5\n", "line-5 THEIRS\n")
        _branches(repo, ours, theirs)
        r = _check(repo, merge_sha=_merge_with_result(repo, ours))
        assert r["verdict"] == "clean", r["dropped"]

    def test_other_side_deleted_the_context_of_an_insertion(self, repo):
        ours = BASE.replace("line-5\n", "line-5\nOURS-NEW\n")
        theirs = BASE.replace("line-4\nline-5\nline-6\n", "")
        _branches(repo, ours, theirs)
        r = _check(repo, merge_sha=_merge_with_result(repo, theirs))
        assert r["verdict"] == "clean", r["dropped"]

    def test_blank_and_rule_lines_are_not_significant(self, repo):
        ours = BASE.replace("line-2\n", "line-2\n\n|---|---|\n")
        _branches(repo, ours, THEIRS_ADD)
        r = _check(repo, merge_sha=_merge_with_result(repo, THEIRS_ADD))
        assert [d["line"] for d in r["dropped"]] == []

    def test_generated_kb_counts_block_is_rederived_not_lost(self, repo):
        block = "<!-- kb-counts:start:x -->\n| Core | {n} |\n<!-- kb-counts:end:x -->\n"
        (repo / "doc.md").write_text(BASE + block.format(n=1))
        _git(repo, "commit", "-qam", "blocks")
        _branches(repo, BASE + block.format(n=2), BASE.replace("line-8\n", "line-8\nT\n") + block.format(n=3))
        r = _check(repo, merge_sha=_merge_with_result(repo, BASE.replace("line-8\n", "line-8\nT\n") + block.format(n=4)))
        assert r["verdict"] == "clean", r["dropped"]

    def test_rendered_file_renumbering_is_skipped_and_reported_not_silent(self, repo):
        hdr = "# Inv\n\n> Generated from `inv.json` by `cli.py --render`.\n\n"
        base = hdr + "| D1 | a |\n| D2 | c |\n"
        (repo / "inv.md").write_text(base)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "rendered")
        ours = hdr + "| D1 | a |\n| D2 | b-ours |\n| D3 | c |\n"
        theirs = hdr + "| D1 | a |\n| D2 | b-theirs |\n| D3 | c |\n"
        _branches(repo, ours, theirs, path="inv.md")
        result = hdr + "| D1 | a |\n| D2 | b-theirs |\n| D3 | b-ours |\n| D4 | c |\n"
        r = _check(repo, merge_sha=_merge_with_result(repo, result, path="inv.md"))
        assert r["verdict"] == "clean", r["dropped"]
        assert any(s["path"] == "inv.md" and "rendered from inv.json" in s["reason"] for s in r["skipped"])

    def test_header_added_only_in_the_merge_does_not_exempt(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD)
        forged = "> Generated from `x.json` by `y`.\n" + OURS_ADD
        r = _check(repo, merge_sha=_merge_with_result(repo, forged))
        assert r["verdict"] == "dropped" and any("THEIRS-NEW" in d["line"] for d in r["dropped"])

    def test_project_history_is_skipped_and_reported_not_silent(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD, path="project-history/x.ndjson")
        r = _check(repo, merge_sha=_merge_with_result(repo, OURS_ADD, path="project-history/x.ndjson"))
        assert r["verdict"] == "clean" and r["checked_files"] == 0
        assert r["skipped"] and "derived" in r["skipped"][0]["reason"]


class TestMergeInProgress:
    def test_dropped_line_in_the_index_is_caught_at_pre_commit_time(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD)
        _git(repo, "merge", "--no-commit", "--no-ff", "theirs", check=False)
        (repo / "doc.md").write_text(OURS_ADD)           # driver left "ours" and the human staged it
        _git(repo, "add", "doc.md")
        r = _check(repo)
        assert r["verdict"] == "dropped" and r["merge_ref"] == "MERGE_HEAD"
        assert r["dropped"][0]["line"] == "THEIRS-NEW"

    def test_unresolved_conflict_is_skipped_not_judged(self, repo):
        ours = BASE.replace("line-5\n", "line-5 OURS\n")
        theirs = BASE.replace("line-5\n", "line-5 THEIRS\n")
        _branches(repo, ours, theirs)
        _git(repo, "merge", "--no-commit", "--no-ff", "theirs", check=False)
        r = _check(repo)
        assert r["checked_files"] == 0 and "conflicted" in r["skipped"][0]["reason"]

    def test_no_merge_is_unmeasurable_never_green(self, repo):
        r = _check(repo)
        assert r["verdict"] == "unmeasurable" and r["ok"] is False and "MERGE_HEAD" in r["error"]

    def test_non_merge_sha_is_unmeasurable(self, repo):
        r = _check(repo, merge_sha="HEAD")
        assert r["verdict"] == "unmeasurable" and "not a merge" in r["error"]


class TestTelemetry:
    def test_every_run_appends_one_row_and_a_drop_files_a_finding(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD)
        sha = _merge_with_result(repo, OURS_ADD)
        rows, findings = [], []
        r = merge_loss_check(worktree_path=repo, merge_sha=sha,
                             ledger_append=lambda name, rs, publish: rows.append((name, rs, publish)),
                             finding_log=lambda **kw: findings.append(kw) or {"ok": True})
        assert [n for n, _, _ in rows] == ["merge-loss-detector.ndjson"]
        row = rows[0][1][0]
        assert {"ts", "merge_sha", "files", "dropped_count", "mode", "verdict"} <= set(row)
        assert row["mode"] == "shadow" and row["dropped_count"] == 1 and row["verdict"] == "dropped"
        assert rows[0][2] is False                       # pre-commit: never touch the network
        assert len(findings) == 1 and findings[0]["kind"] == "finding" and findings[0]["target"] == "doc.md"
        assert findings[0]["source"]["tool"] == "noctus.dev.merge_loss_check"
        assert r["telemetry"] == "logged" and r["finding"] == "logged"

    def test_clean_run_logs_a_row_but_no_finding(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD)
        sha = _merge_with_result(repo, BOTH)
        rows, findings = [], []
        merge_loss_check(worktree_path=repo, merge_sha=sha, ledger_append=lambda n, rs, publish: rows.append(rs),
                         finding_log=lambda **kw: findings.append(kw))
        assert len(rows) == 1 and rows[0][0]["verdict"] == "clean" and findings == []

    def test_telemetry_failure_never_fails_the_check(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD)
        sha = _merge_with_result(repo, OURS_ADD)

        def boom(*a, **k):
            raise OSError("disk full")
        r = merge_loss_check(worktree_path=repo, merge_sha=sha, ledger_append=boom, finding_log=boom)
        assert r["verdict"] == "dropped" and r["telemetry"].startswith("failed") and r["finding"].startswith("failed")


class TestSurface:
    def test_tool_is_registered(self):
        names = []

        class S:
            def tool(self, name, description):
                names.append(name)
                return lambda f: f
        merge_loss.register(S())
        assert names == ["noctus.dev.merge_loss_check"]

    def test_cli_flag_is_shadow_exit_zero_even_on_a_drop(self, repo):
        _branches(repo, OURS_ADD, THEIRS_ADD)
        sha = _merge_with_result(repo, OURS_ADD)
        p = subprocess.run([sys.executable, str(REPO / "mcp/noctusai/cli.py"), "--check-merge-loss", "--no-log",
                            "--merge-sha", sha, "--worktree-path", str(repo)], capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        out = p.stdout[p.stdout.index("{\n"):]
        assert json.loads(out)["verdict"] == "dropped" and "SHADOW" in p.stderr
