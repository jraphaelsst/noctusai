"""Regression suite for keeper `check_lgpd_entry_removal` (commit-time leg) and
`check_lgpd_entry_removal_range` (CI leg).

MUTATION PROOF: the fixtures under tests/fixtures/lgpd/ are the REAL blobs of the
2026-10-10 incident (`git show 7c2667c83^:LGPD-WARNINGS.md` / `7c2667c83:...`),
a commit that REPLACED the core-transcription-API entry with a new one. The
keeper must refuse that exact change; the same replay with the override trailer,
a tick to `- [x]`, and an in-place mitigation edit must pass.

→ KB § PATTERNS/common/lgpd-entry-keeper.md
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.lgpd import parse_warnings  # noqa: E402
from tools.noctus.dev.compliance import (  # noqa: E402
    check_lgpd_entry_removal,
    check_lgpd_entry_removal_range,
    lgpd_removal_overrides,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "lgpd"
PRE = (FIX / "pre-7c2667c83.md").read_text(encoding="utf-8")
POST = (FIX / "post-7c2667c83.md").read_text(encoding="utf-8")
TRANSCRIPTION = "Platform transcription API (core) stores voice audio"
TRAILER = (
    "docs(lgpd): replay\n\n"
    "LGPD-Entry-Removed: Platform transcription API (core) — duplicate of the re-filed entry\n"
)


_TRANSCRIPTION_BLOCK = next(b for b in parse_warnings(PRE)[1] if TRANSCRIPTION in b)


def _with_entry(text: str, block: str) -> str:
    """`text` with ``block`` inserted at the top of the list (what flag() does)."""
    header, blocks = parse_warnings(text)
    return header + "\n".join(b.rstrip() for b in [block, *blocks]) + "\n"


HEALED = _with_entry(POST, _TRANSCRIPTION_BLOCK)  # the incident, re-filed (c12dfca47)


def _issues(parent: str, new: str, msg: str | None = None) -> list[dict]:
    return check_lgpd_entry_removal(parent_texts=[parent], new_text=new, commit_message=msg)


class TestCheckLgpdEntryRemoval:
    def test_fixtures_are_the_real_incident(self):
        assert TRANSCRIPTION in PRE and TRANSCRIPTION not in POST

    def test_mutation_proof_replay_of_7c2667c83_is_refused(self):
        out = _issues(PRE, POST, "docs(lgpd): flag third-party reel transcription")
        assert len(out) == 1 and out[0]["severity"] == "high"
        assert "Platform transcription API (core)" in out[0]["issue"]
        assert "LGPD-Entry-Removed" in out[0]["issue"]  # the message names the override

    def test_replay_with_override_trailer_passes(self):
        assert _issues(PRE, POST, TRAILER) == []

    def test_ascii_double_dash_trailer_and_path_prefix_selector_pass(self):
        msg = "x\n\nLGPD-Entry-Removed: products/core/backend/app/services/transcription_api -- dup\n"
        assert _issues(PRE, POST, msg) == []

    def test_trailer_without_reason_does_not_count(self):
        assert _issues(PRE, POST, "x\n\nLGPD-Entry-Removed: Platform transcription API (core)\n")
        assert _issues(PRE, POST, "x\n\nLGPD-Entry-Removed: Platform transcription API (core) —\n")

    def test_too_short_selector_is_ignored(self):
        assert _issues(PRE, POST, "x\n\nLGPD-Entry-Removed: Plat — because\n")
        assert lgpd_removal_overrides("LGPD-Entry-Removed: Plat — because") == []

    def test_trailer_for_another_entry_does_not_cover_this_one(self):
        assert _issues(PRE, POST, "x\n\nLGPD-Entry-Removed: Uploaded brain source files — dup\n")

    def test_tick_to_resolved_passes(self):
        ticked = PRE.replace(f"- [ ] **{TRANSCRIPTION}", f"- [x] **{TRANSCRIPTION}", 1)
        assert ticked != PRE
        assert _issues(PRE, ticked) == []

    def test_in_place_mitigation_edit_passes(self):
        edited = PRE.replace("  - *Mitigation*: Implemented:", "  - *Mitigation*: EDITED in place. Implemented:", 1)
        assert edited != PRE
        assert _issues(PRE, edited) == []

    def test_adding_entries_passes(self):
        assert _issues(POST, HEALED) == []

    def test_changing_concern_text_reads_as_remove_plus_add(self):
        rekeyed = PRE.replace(f"**{TRANSCRIPTION}", "**RENAMED " + TRANSCRIPTION, 1)
        assert _issues(PRE, rekeyed)
        assert _issues(PRE, rekeyed, TRAILER) == []

    def test_removing_an_already_resolved_entry_is_allowed(self):
        ticked = PRE.replace(f"- [ ] **{TRANSCRIPTION}", f"- [x] **{TRANSCRIPTION}", 1)
        assert _issues(ticked, POST) == []

    def test_deleting_the_whole_file_is_refused(self):
        assert _issues(PRE, "")

    def test_new_file_or_no_parent_is_a_noop(self):
        assert check_lgpd_entry_removal(parent_texts=[None], new_text=POST) == []

    def test_every_refused_entry_is_named(self):
        out = _issues(PRE, PRE.split("- [ ]", 1)[0])  # drop ALL entries
        assert "Platform transcription API (core)" in out[0]["issue"]
        assert "Uploaded brain source files" in out[0]["issue"]

    def test_merge_resolution_losing_a_sides_addition_is_refused(self):
        # ancestor lacks the entry; one parent ADDED it; the resolution dropped it.
        out = check_lgpd_entry_removal(parent_texts=[HEALED, POST], new_text=POST, ancestor_text=POST)
        assert out and "Platform transcription API (core)" in out[0]["issue"]

    def test_merge_accepting_the_other_sides_deletion_is_not_a_loss(self):
        # the entry is IN the ancestor and one side deleted it: that delete was that
        # side's own (keeper-governed) commit, not this merge's.
        assert check_lgpd_entry_removal(
            parent_texts=[HEALED, POST], new_text=POST, ancestor_text=HEALED) == []


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True,
                          capture_output=True, text=True, env=env).stdout


def _commit(repo: Path, text: str, msg: str) -> str:
    (repo / "LGPD-WARNINGS.md").write_text(text, encoding="utf-8")
    _git(repo, "add", "LGPD-WARNINGS.md")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    return repo


class TestCheckLgpdEntryRemovalStaged:
    """Commit-time leg against a REAL index / HEAD."""

    def test_staged_replay_is_refused_then_passes_with_trailer(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, PRE, "base")
        (repo / "LGPD-WARNINGS.md").write_text(POST, encoding="utf-8")
        _git(repo, "add", "LGPD-WARNINGS.md")
        assert check_lgpd_entry_removal(repo_root=repo, commit_message="docs(lgpd): x")
        assert check_lgpd_entry_removal(repo_root=repo, commit_message=TRAILER) == []

    def test_staged_tick_passes(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, PRE, "base")
        ticked = PRE.replace(f"- [ ] **{TRANSCRIPTION}", f"- [x] **{TRANSCRIPTION}", 1)
        (repo / "LGPD-WARNINGS.md").write_text(ticked, encoding="utf-8")
        _git(repo, "add", "LGPD-WARNINGS.md")
        assert check_lgpd_entry_removal(repo_root=repo, commit_message="tick") == []

    def test_first_commit_with_no_head_is_a_noop(self, tmp_path):
        repo = _repo(tmp_path)
        (repo / "LGPD-WARNINGS.md").write_text(POST, encoding="utf-8")
        _git(repo, "add", "LGPD-WARNINGS.md")
        assert check_lgpd_entry_removal(repo_root=repo, commit_message="init") == []

    def test_mid_merge_resolution_that_drops_the_other_side_is_refused(self, tmp_path):
        repo = _repo(tmp_path)
        base = _commit(repo, POST, "base")
        _git(repo, "checkout", "-q", "-b", "other")
        _commit(repo, PRE, "other adds the transcription entry")
        _git(repo, "checkout", "-q", "main")
        _commit(repo, POST + "\n", "main touches the file")  # force a real merge
        _git(repo, "merge", "--no-commit", "--no-ff", "-X", "ours", "other")
        # resolution = ours: silently drops other's addition (the incident shape)
        (repo / "LGPD-WARNINGS.md").write_text(POST, encoding="utf-8")
        _git(repo, "add", "LGPD-WARNINGS.md")
        out = check_lgpd_entry_removal(repo_root=repo, commit_message="Merge other")
        assert out and "Platform transcription API (core)" in out[0]["issue"]
        assert base


class TestCheckLgpdEntryRemovalRange:
    """CI leg: each commit of the range vs its parent with its OWN message."""

    def test_replayed_incident_commit_is_refused_and_named(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, PRE, "base")
        sha = _commit(repo, POST, "docs(lgpd): replay of 7c2667c83")
        out = check_lgpd_entry_removal_range("HEAD~1..HEAD", repo_root=repo)
        assert len(out) == 1 and sha[:9] in out[0]["issue"]

    def test_replay_with_its_own_trailer_passes(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, PRE, "base")
        _commit(repo, POST, TRAILER)
        assert check_lgpd_entry_removal_range("HEAD~1..HEAD", repo_root=repo) == []

    def test_trailer_on_a_different_commit_does_not_cover_it(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, PRE, "base")
        _commit(repo, POST, "replay without trailer")
        _commit(repo, POST + "\n", TRAILER)  # trailer rides on the NEXT commit
        out = check_lgpd_entry_removal_range("HEAD~2..HEAD", repo_root=repo)
        assert len(out) == 1

    def test_removal_re_filed_later_in_the_range_is_forgiven(self, tmp_path):
        """The real history: 7c2667c83 dropped it, c12dfca47 re-filed it. A dev->main
        fast-forward carrying both must not wedge on the already-healed incident."""
        repo = _repo(tmp_path)
        _commit(repo, PRE, "base")
        _commit(repo, POST, "the incident")
        _commit(repo, HEALED, "re-file")
        assert check_lgpd_entry_removal_range("HEAD~2..HEAD", repo_root=repo) == []
        assert check_lgpd_entry_removal_range("HEAD~2..HEAD~1", repo_root=repo)

    def test_merge_commit_that_loses_a_branch_addition_is_refused(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, POST, "base")
        _git(repo, "checkout", "-q", "-b", "feat")
        _commit(repo, PRE, "feat adds the transcription entry")
        _git(repo, "checkout", "-q", "main")
        _commit(repo, POST + "\n", "main moves")
        _git(repo, "merge", "-q", "-s", "ours", "--no-edit", "feat")  # drops feat's entry
        out = check_lgpd_entry_removal_range("main~2..main", repo_root=repo)
        assert out and "Platform transcription API (core)" in out[0]["issue"]

    def test_accepted_historical_sha_is_skipped(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, PRE, "base")
        sha = _commit(repo, POST, "the incident")
        assert check_lgpd_entry_removal_range("HEAD~1..HEAD", repo_root=repo)
        assert check_lgpd_entry_removal_range(
            "HEAD~1..HEAD", repo_root=repo, accepted={sha: "re-filed under a new text"}) == []

    def test_the_real_incident_commit_is_on_the_accepted_list(self):
        from tools.noctus.dev.compliance import _LGPD_ACCEPTED_HISTORICAL
        assert "7c2667c834d59bf76fdc9940febb8281b6b8e010" in _LGPD_ACCEPTED_HISTORICAL

    def test_unresolvable_range_fails_closed(self, tmp_path):
        repo = _repo(tmp_path)
        _commit(repo, PRE, "base")
        assert check_lgpd_entry_removal_range("nope..HEAD", repo_root=repo)
        assert check_lgpd_entry_removal_range("HEAD", repo_root=repo)  # not a range
