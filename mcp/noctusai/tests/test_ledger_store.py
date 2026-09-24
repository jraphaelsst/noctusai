"""Tests for `_ledger_store` — Real (plumbing on a temp BARE repo, no network),
Fake (file-backed), the factory, and the dual-read merge."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _ledger_store as ls  # noqa: E402


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"git {args} failed: {r.stderr}"
    return r.stdout


def _clone(bare: Path, dest: Path) -> Path:
    subprocess.run(["git", "clone", "-q", str(bare), str(dest)], check=True, capture_output=True)
    _git(dest, "config", "user.email", "t@example.com")
    _git(dest, "config", "user.name", "t")
    return dest


@pytest.fixture
def repos(tmp_path):
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    seed = _clone(bare, tmp_path / "seed")
    (seed / "README.md").write_text("x\n")
    _git(seed, "add", "README.md")
    _git(seed, "commit", "-qm", "init")
    _git(seed, "push", "-q", "origin", "HEAD:refs/heads/dev")
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/dev")
    a = _clone(bare, tmp_path / "a")
    b = _clone(bare, tmp_path / "b")
    return bare, a, b


def _store(repo: Path, **kw) -> ls.GitLedgerStore:
    return ls.GitLedgerStore(repo_root=repo, backoff_s=0, **kw)


def _bootstrap(repo: Path, seed: dict[str, str] | None = None) -> dict:
    return _store(repo).bootstrap(seed or {"x.ndjson": '{"n":0}\n'}, message="seed")


class TestBootstrap:
    def test_creates_orphan_branch(self, repos):
        bare, a, _ = repos
        r = _bootstrap(a)
        assert r["ok"] and r["status"] == "created"
        # orphan: no parents, and unrelated to dev
        parents = _git(bare, "rev-list", "--parents", "-n1", "refs/heads/ledgers").split()
        assert len(parents) == 1
        assert _git(bare, "show", "refs/heads/ledgers:x.ndjson") == '{"n":0}\n'

    def test_refuses_when_exists(self, repos):
        _, a, b = repos
        assert _bootstrap(a)["ok"]
        r = _bootstrap(b)
        assert r["ok"] is False and r["status"] == "exists"

    def test_never_touches_worktree_or_index(self, repos):
        _, a, _ = repos
        before = _git(a, "status", "--porcelain"), _git(a, "rev-parse", "HEAD")
        _bootstrap(a)
        _store(a).append("x.ndjson", ['{"n":1}'], message="m")
        assert (_git(a, "status", "--porcelain"), _git(a, "rev-parse", "HEAD")) == before


class TestAppendRead:
    def test_append_publishes_and_reads_back(self, repos):
        bare, a, b = repos
        _bootstrap(a)
        r = _store(a).append("x.ndjson", ['{"n":1}'], message="row")
        assert r["ok"] and r["status"] == "pushed", r
        assert _git(bare, "show", "refs/heads/ledgers:x.ndjson").splitlines() == ['{"n":0}', '{"n":1}']
        # another clone sees it after a fetch
        assert _store(b).read_text("x.ndjson", fetch=True).splitlines()[-1] == '{"n":1}'
        subject = _git(bare, "log", "-1", "--format=%s", "refs/heads/ledgers")
        assert subject.startswith("ledger(x.ndjson): row")

    def test_new_file_is_created(self, repos):
        bare, a, _ = repos
        _bootstrap(a)
        assert _store(a).append("y.ndjson", ['{"y":1}'], message="m")["ok"]
        assert _git(bare, "show", "refs/heads/ledgers:y.ndjson") == '{"y":1}\n'
        assert _git(bare, "show", "refs/heads/ledgers:x.ndjson") == '{"n":0}\n'

    def test_race_between_clones_is_retried_not_lost(self, repos):
        bare, a, b = repos
        _bootstrap(a)
        sa, sb = _store(a), _store(b)
        sb.fetch()
        # b's tracking ref is now stale relative to a's push below; b must
        # re-fetch + rebuild on the rejected push instead of dropping its row.
        assert sa.append("x.ndjson", ['{"from":"a"}'], message="a")["ok"]
        rb = sb.append("x.ndjson", ['{"from":"b"}'], message="b")
        assert rb["ok"], rb
        lines = _git(bare, "show", "refs/heads/ledgers:x.ndjson").splitlines()
        assert '{"from":"a"}' in lines and '{"from":"b"}' in lines

    def test_concurrent_threads_same_clone(self, repos):
        bare, a, _ = repos
        _bootstrap(a)
        s = _store(a)
        errs: list = []

        def w(i):
            r = s.append("x.ndjson", [json.dumps({"i": i})], message=f"t{i}")
            if not r["ok"]:
                errs.append(r)

        ts = [threading.Thread(target=w, args=(i,)) for i in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert not errs
        lines = _git(bare, "show", "refs/heads/ledgers:x.ndjson").splitlines()
        assert sorted(json.loads(x).get("i", -1) for x in lines) == [-1, 0, 1, 2, 3, 4, 5]

    def test_offline_spools_and_reads_own_write_then_flushes(self, repos, tmp_path):
        bare, a, _ = repos
        _bootstrap(a)
        s = _store(a, max_attempts=2)
        _git(a, "remote", "set-url", "origin", str(tmp_path / "nowhere.git"))
        r = s.append("x.ndjson", ['{"n":9}'], message="offline")
        assert r["ok"] is False and r["status"] == "pending" and r["spooled"] == ["x.ndjson"]
        assert '{"n":9}' in s.read_text("x.ndjson").splitlines()   # read-your-writes
        _git(a, "remote", "set-url", "origin", str(bare))
        f = s.flush()
        assert f["ok"] and f["status"] == "pushed"
        assert _git(bare, "show", "refs/heads/ledgers:x.ndjson").splitlines()[-1] == '{"n":9}'
        assert s.pending_text("x.ndjson") == ""

    def test_spooled_row_already_on_branch_is_not_duplicated(self, repos):
        bare, a, _ = repos
        _bootstrap(a)
        s = _store(a)
        (s.pending_dir() / "x.ndjson").write_text('{"n":0}\n')   # crash-after-push shape
        r = s.flush()
        assert r["status"] == "unchanged"
        assert _git(bare, "show", "refs/heads/ledgers:x.ndjson") == '{"n":0}\n'

    def test_publish_false_only_spools(self, repos):
        bare, a, _ = repos
        _bootstrap(a)
        s = _store(a)
        r = s.append("x.ndjson", ['{"n":2}'], message="m", publish=False)
        assert r["status"] == "spooled"
        assert _git(bare, "show", "refs/heads/ledgers:x.ndjson") == '{"n":0}\n'
        assert s.flush()["status"] == "pushed"

    def test_read_without_branch_raises(self, repos):
        _, a, _ = repos
        with pytest.raises(ls.LedgerStoreError):
            _store(a).read_text("x.ndjson")

    def test_rejects_bad_names_and_multiline_rows(self, repos):
        _, a, _ = repos
        _bootstrap(a)
        with pytest.raises(ValueError):
            _store(a).append("../evil.ndjson", ["{}"], message="m")
        with pytest.raises(ValueError):
            _store(a).append("x.ndjson", ["{}\n{}"], message="m")


class TestUpdate:
    def test_update_rewrites_whole_file(self, repos):
        bare, a, _ = repos
        _bootstrap(a, {"x.ndjson": '{"s":"old"}\n'})
        r = _store(a).update("x.ndjson", lambda t: t.replace("old", "new"), message="promote")
        assert r["ok"] and r["status"] == "pushed"
        assert _git(bare, "show", "refs/heads/ledgers:x.ndjson") == '{"s":"new"}\n'

    def test_noop_transform_makes_no_commit(self, repos):
        bare, a, _ = repos
        _bootstrap(a)
        before = _git(bare, "rev-parse", "refs/heads/ledgers")
        assert _store(a).update("x.ndjson", lambda t: t, message="m")["status"] == "unchanged"
        assert _git(bare, "rev-parse", "refs/heads/ledgers") == before


class TestFakeAndFactory:
    def test_file_ledger_roundtrip(self, tmp_path):
        led = ls.FileLedger(name="x.ndjson", path=tmp_path / "ph" / "x.ndjson")
        assert led.read_text() == ""
        led.append(['{"a":1}'], message="m")
        led.append(['{"a":2}'], message="m")
        assert led.read_text().splitlines() == ['{"a":1}', '{"a":2}']
        led.update(lambda t: t.replace("2", "3"), message="m")
        assert led.read_text().splitlines() == ['{"a":1}', '{"a":3}']

    def test_suite_runs_in_fake_mode(self, tmp_path):
        # conftest pins the suite to the Fake so no test can push to origin.
        assert ls.store_mode() == ls.MODE_FAKE
        assert isinstance(ls.open_ledger("x.ndjson", tmp_path / "x.ndjson"), ls.FileLedger)

    def test_factory_git_mode(self, tmp_path, monkeypatch):
        monkeypatch.setenv(ls.ENV_MODE, "git")
        led = ls.open_ledger("x.ndjson", tmp_path / "x.ndjson", repo_root=tmp_path)
        assert isinstance(led, ls.GitLedger) and led.store.repo_root == tmp_path

    def test_factory_rejects_unknown_mode(self, tmp_path, monkeypatch):
        monkeypatch.setenv(ls.ENV_MODE, "s3")
        with pytest.raises(ValueError):
            ls.open_ledger("x.ndjson", tmp_path / "x.ndjson")

    def test_protocol_conformance(self, tmp_path):
        assert isinstance(ls.FileLedger("x.ndjson", tmp_path / "x"), ls.Ledger)
        assert isinstance(ls.GitLedger("x.ndjson", ls.GitLedgerStore(tmp_path)), ls.Ledger)


class TestMerge:
    def test_union_dedupes_exact_lines_preserving_order(self):
        dev = '{"a":1}\n{"a":2}\n'
        br = '{"a":1}\n{"a":3}\n'
        assert ls.merge_ndjson_text(dev, br).splitlines() == ['{"a":1}', '{"a":2}', '{"a":3}']

    def test_keyed_later_source_wins_in_place(self):
        k = lambda e: (e["ts"], e["t"])  # noqa: E731
        dev = '{"ts":"1","t":"x","s":"old"}\n{"ts":"2","t":"y","s":"old"}\n'
        br = '{"ts":"1","t":"x","s":"new"}\n'
        out = ls.merge_ndjson_text(dev, br, key=k).splitlines()
        assert [json.loads(x)["s"] for x in out] == ["new", "old"]

    def test_malformed_lines_survive(self):
        assert "not json" in ls.merge_ndjson_text("not json\n", "", key=lambda e: e["x"])

    def test_read_dual_surfaces_store_error(self, repos):
        _, a, _ = repos
        led = ls.GitLedger("x.ndjson", _store(a))   # no branch bootstrapped
        text, err = ls.read_dual(led, '{"d":1}\n')
        assert text == '{"d":1}\n' and err and "not found" in err


class TestTool:
    def _dev_with_ledgers(self, repos):
        bare, a, b = repos
        (a / "project-history").mkdir()
        (a / "project-history" / "branch-tree.ndjson").write_text('{"branch":"x"}\n')
        (a / "project-history" / "ledger.ndjson").write_text('{"stays":"on dev"}\n')
        _git(a, "add", "project-history")
        _git(a, "commit", "-qm", "ledgers")
        _git(a, "push", "-q", "origin", "HEAD:dev")
        return bare, a, b

    def test_bootstrap_dry_run_then_confirm(self, repos):
        from tools.noctus.dev.ledger_store import ledger_store
        bare, a, b = self._dev_with_ledgers(repos)
        plan = ledger_store("bootstrap", repo_root=str(b))
        assert plan["dry_run"] and plan["files"]["branch-tree.ndjson"] == 1
        assert "ledger.ndjson" not in plan["files"]          # the human history stays on dev
        assert _git(bare, "branch", "--list", "ledgers") == ""
        done = ledger_store("bootstrap", confirm=True, repo_root=str(b))
        assert done["ok"] and done["status"] == "created"
        assert _git(bare, "show", "ledgers:branch-tree.ndjson") == '{"branch":"x"}\n'
        assert "never force-push" in _git(bare, "show", "ledgers:README.md")
        again = ledger_store("bootstrap", confirm=True, repo_root=str(b))
        assert again["ok"] is False and again["status"] == "exists"

    def test_status_and_read(self, repos):
        from tools.noctus.dev.ledger_store import ledger_store
        bare, a, b = self._dev_with_ledgers(repos)
        ledger_store("bootstrap", confirm=True, repo_root=str(b))
        _store(b).append("branch-tree.ndjson", ['{"branch":"y"}'], message="m")
        st = ledger_store("status", repo_root=str(a))
        assert st["ok"] and st["ledgers"]["branch-tree.ndjson"]["rows"] == 2
        rd = ledger_store("read", name="branch-tree.ndjson", repo_root=str(a))
        assert rd["ok"] and rd["rows"] == 2 and rd["tail"][-1] == '{"branch":"y"}'

    def test_status_without_branch_is_not_ok(self, repos):
        from tools.noctus.dev.ledger_store import ledger_store
        _, a, _ = repos
        st = ledger_store("status", repo_root=str(a))
        assert st["ok"] is False and "bootstrap" in st["error"]


class TestPrePushLedgersGuard:
    """scripts/hooks/pre-push: a ledgers-only push skips the refresh/keeper tax
    but deleting or rewinding `ledgers` is always refused."""

    HOOK = Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "pre-push"
    Z = "0" * 40

    def _run(self, repo: Path, line: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(self.HOOK), "origin", "url"], cwd=str(repo),
                              input=line + "\n", capture_output=True, text=True, timeout=60)

    def _two_commits(self, repo: Path) -> tuple[str, str]:
        _git(repo, "commit", "-q", "--allow-empty", "-m", "one")
        one = _git(repo, "rev-parse", "HEAD").strip()
        _git(repo, "commit", "-q", "--allow-empty", "-m", "two")
        return one, _git(repo, "rev-parse", "HEAD").strip()

    def test_fast_forward_passes(self, repos):
        _, a, _ = repos
        one, two = self._two_commits(a)
        r = self._run(a, f"{two} {two} refs/heads/ledgers {one}")
        assert r.returncode == 0, r.stderr
        assert "branch-tree mirror" not in r.stdout + r.stderr   # keepers skipped

    def test_delete_refused(self, repos):
        _, a, _ = repos
        one, _two = self._two_commits(a)
        r = self._run(a, f"(delete) {self.Z} refs/heads/ledgers {one}")
        assert r.returncode == 1 and "DELETE 'ledgers'" in r.stderr

    def test_rewind_refused(self, repos):
        _, a, _ = repos
        one, two = self._two_commits(a)
        r = self._run(a, f"{one} {one} refs/heads/ledgers {two}")
        assert r.returncode == 1 and "NON-FAST-FORWARD push to 'ledgers'" in r.stderr
