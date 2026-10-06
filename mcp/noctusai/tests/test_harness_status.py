"""noctus.dev.harness_status / harness_event — real git fixture repos, no
monkeypatching of our own code (DI seams + a real tmp ledger via LEDGER_PATH
env-free fixtures like test_auto_improvement)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import harness_status as hs  # noqa: E402
from tools.noctus.dev import auto_improvement as ai  # noqa: E402


def _g(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                        "HOME": str(cwd)})


@pytest.fixture
def repo(tmp_path):
    """primary repo with a bare origin: main, dev (1 ahead of main), local dev 1 ahead."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    _g(origin, "init", "--bare", "-b", "main")
    primary = tmp_path / "primary"
    primary.mkdir()
    _g(primary, "init", "-b", "main")
    _g(primary, "remote", "add", "origin", str(origin))
    (primary / "a.txt").write_text("a")
    _g(primary, "add", ".")
    _g(primary, "commit", "-m", "init")
    _g(primary, "push", "origin", "main")
    _g(primary, "checkout", "-b", "dev")
    (primary / "b.txt").write_text("b")
    _g(primary, "add", ".")
    _g(primary, "commit", "-m", "dev1")
    _g(primary, "push", "origin", "dev")
    (primary / "c.txt").write_text("c")
    _g(primary, "add", ".")
    _g(primary, "commit", "-m", "local-only")
    return primary


@pytest.fixture
def memdir(tmp_path):
    d = tmp_path / "mem"
    d.mkdir()
    (d / "MEMORY-reminders.md").write_text(
        "# x\n\n- [Reminder one](r1.md)\n- [Reminder two](r2.md)\n> not a reminder\n")
    return d


class TestFast:
    def test_primary_tree_and_dev_drift(self, repo, memdir):
        out = hs.harness_status(cwd=str(repo), memory_dir=memdir)
        assert out["schema"] == "noc.harness_status/v1"
        assert out["mode"] == "fast"
        assert out["repo_root"] == str(repo.resolve())
        s = out["session"]
        assert (s["tree"], s["branch"], s["is_shared_branch"]) == ("primary", "dev", True)
        assert out["dev"] == {"local_ahead": 1, "local_behind": 0, "dev_ahead_of_main": 1}
        assert out["reminders"] == [{"title": "Reminder one", "file": "r1.md"},
                                    {"title": "Reminder two", "file": "r2.md"}]
        assert out["errors"] == []

    def test_full_keys_are_null_in_fast_mode(self, repo, memdir):
        out = hs.harness_status(cwd=str(repo), memory_dir=memdir)
        for k in ("caches", "auto_improvement", "branch_pointers", "worktrees", "dispatcher_pending"):
            assert k in out and out[k] is None

    def test_worktree_session_and_dirty(self, repo, memdir):
        wt = repo / ".claude" / "worktrees" / "slug1"
        _g(repo, "worktree", "add", "-b", "feat/slug1", str(wt), "dev")
        (wt / "new.txt").write_text("x")
        out = hs.harness_status(cwd=str(wt), memory_dir=memdir)
        s = out["session"]
        assert (s["tree"], s["worktree_slug"], s["branch"]) == ("worktree", "slug1", "feat/slug1")
        assert s["is_shared_branch"] is False and s["dirty"] == 1
        assert out["repo_root"] == str(repo.resolve())

    def test_outside_git(self, tmp_path, memdir):
        outside = tmp_path / "nowhere"
        outside.mkdir()
        out = hs.harness_status(cwd=str(outside), memory_dir=memdir)
        assert out["session"]["tree"] == "outside"
        assert any(e["section"] == "repo_root" for e in out["errors"])

    def test_missing_memory_dir_is_an_error_not_silent(self, repo, tmp_path):
        out = hs.harness_status(cwd=str(repo), memory_dir=tmp_path / "absent")
        assert out["reminders"] == []
        assert [e["section"] for e in out["errors"]] == ["reminders"]

    def test_missing_origin_refs_error_but_never_raise(self, tmp_path, memdir):
        r = tmp_path / "solo"
        r.mkdir()
        _g(r, "init", "-b", "dev")
        (r / "f").write_text("f")
        _g(r, "add", ".")
        _g(r, "commit", "-m", "i")
        out = hs.harness_status(cwd=str(r), memory_dir=memdir)
        assert any(e["section"] == "dev" for e in out["errors"])
        assert out["session"]["branch"] == "dev"


class TestFull:
    def test_failing_section_lands_in_errors_others_survive(self, repo, memdir):
        def boom():
            raise RuntimeError("cache keeper exploded")
        out = hs.harness_status(full=True, cwd=str(repo), memory_dir=memdir,
                                section_overrides={
                                    "caches": boom,
                                    "auto_improvement": lambda: {"open_s1": 1, "open_s2": 0, "top": []},
                                    "branch_pointers": lambda: [],
                                })
        assert out["mode"] == "full"
        assert out["caches"] is None
        assert {"section": "caches", "error": "RuntimeError: cache keeper exploded"} in out["errors"]
        assert out["auto_improvement"]["open_s1"] == 1
        assert out["branch_pointers"] == []
        assert out["worktrees"] == []
        assert out["dispatcher_pending"] == 0

    def test_worktrees_and_dispatcher(self, repo, memdir):
        wt = repo / ".claude" / "worktrees" / "w2"
        _g(repo, "worktree", "add", "-b", "feat/w2", str(wt), "dev")
        _g(repo, "update-ref", "refs/remotes/origin/dev", "dev")
        (repo / ".claude" / "dispatcher.md").write_text(
            "# d\n## Pending\n- one\n- two\n## Done\n- three\n")
        out = hs.harness_status(full=True, cwd=str(repo), memory_dir=memdir,
                                section_overrides={"caches": lambda: None,
                                                   "auto_improvement": lambda: None,
                                                   "branch_pointers": lambda: None})
        assert out["dispatcher_pending"] == 2
        assert [w["slug"] for w in out["worktrees"]] == ["w2"]
        assert out["worktrees"][0]["branch"] == "feat/w2"
        assert out["worktrees"][0]["ahead_of_dev"] == 0


@pytest.fixture
def ai_ledger(tmp_path, monkeypatch):
    # same tmp-ledger seam test_auto_improvement uses (storage path, not a guard)
    monkeypatch.setattr(ai, "CACHE_DIR", tmp_path / "c")
    monkeypatch.setattr(ai, "CACHE_PATH", tmp_path / "c" / "ai.sqlite")
    monkeypatch.setattr(ai, "LEDGER_PATH", tmp_path / "project-history" / "auto-improvement.ndjson")
    return ai.LEDGER_PATH


class TestEvent:
    def test_logs_s1_entry_via_existing_ledger(self, ai_ledger):
        r = hs.harness_event({"kind": "gate_denied", "target": "primary_write_guard",
                              "summary": "write denied", "detail": "d", "session_id": "S1",
                              "source": "noc-harness-mod"})
        assert r["status"] == "logged" and r["id"]
        rows = [json.loads(line) for line in ai_ledger.read_text().splitlines() if line.strip()]
        row = rows[-1]
        assert row["status"] == "s1-emergent" and row["target"] == "primary_write_guard"
        assert row["description"].startswith("[gate_denied] write denied") and "d" in row["description"]
        assert row["agent"] == "noc-harness-mod" and row["source_ref"] == "session:S1"

    @pytest.mark.parametrize("payload", [
        {"kind": "bogus", "target": "t", "summary": "s"},
        {"target": "t", "summary": "s"},
        {"kind": "note", "summary": "s"},
        {"kind": "note", "target": "t", "summary": " "},
        ["not", "an", "object"],
    ])
    def test_refuses_invalid_payload_loudly(self, payload, ai_ledger):
        r = hs.harness_event(payload)
        assert r["status"] == "error" and r["error"]
        assert not ai_ledger.exists()
