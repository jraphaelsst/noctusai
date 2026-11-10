"""Council blind-recorder read guard (must-fix J): pure `decide` + the real hook (enforce denies, shadow warns, fails closed)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / "scripts" / "hooks" / "claude-guard-council-read.py"
_spec = importlib.util.spec_from_file_location("crg_ut", REPO_ROOT / "mcp/noctusai/tools/noctus/dev/council_read_guard.py")
crg = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = crg
_spec.loader.exec_module(crg)

OPEN = "11111111-1111-4111-8111-111111111111"
DONE = "22222222-2222-4222-8222-222222222222"


def _tree(tmp_path, *, open_=True):
    d = tmp_path / "project-history/council/2026-11"
    d.mkdir(parents=True)
    if open_:
        (d / f"{OPEN}.ndjson").write_text(json.dumps({"record": "session", "session_id": OPEN}) + "\n")
    (d / f"{DONE}.ndjson").write_text(
        json.dumps({"record": "session", "session_id": DONE}) + "\n" + json.dumps({"record": "verdict"}) + "\n")
    return tmp_path


def _d(tmp_path, tool, **ti):
    return crg.decide(tool, ti, [tmp_path])


class TestReads:
    def test_open_session_file_denied(self, tmp_path):
        _tree(tmp_path)
        v = _d(tmp_path, "Read", file_path=f"{tmp_path}/project-history/council/2026-11/{OPEN}.ndjson")
        assert v and OPEN in v["session_ids"] and "blind_view" in v["reason"]

    def test_verdicted_session_file_allowed(self, tmp_path):
        _tree(tmp_path)
        assert _d(tmp_path, "Read", file_path=f"{tmp_path}/project-history/council/2026-11/{DONE}.ndjson") is None

    def test_directory_and_globs_denied_while_any_open(self, tmp_path):
        _tree(tmp_path)
        assert _d(tmp_path, "Grep", path="project-history/council", pattern="claim")
        assert _d(tmp_path, "Grep", path=".", glob="project-history/council/**/*.ndjson", pattern="x")
        assert _d(tmp_path, "Glob", pattern="project-history/council/**/*.ndjson")
        assert _d(tmp_path, "Read", file_path="project-history/council/2026-11/x.ndjson")

    def test_nothing_denied_when_every_session_has_a_verdict(self, tmp_path):
        _tree(tmp_path, open_=False)
        assert _d(tmp_path, "Grep", path="project-history/council", pattern="claim") is None

    def test_unparseable_file_counts_as_open(self, tmp_path):
        d = tmp_path / "project-history/council/2026-11"
        d.mkdir(parents=True)
        (d / f"{OPEN}.ndjson").write_text("{not json\n")
        assert _d(tmp_path, "Read", file_path=str(d / f"{OPEN}.ndjson"))

    def test_unrelated_paths_and_tools_pass(self, tmp_path):
        _tree(tmp_path)
        assert _d(tmp_path, "Read", file_path="products/core/x.py") is None
        assert _d(tmp_path, "Grep", path="project-history", pattern="x") is None  # documented limit: ancestor grep
        assert _d(tmp_path, "Write", file_path="project-history/council/x") is None


class TestBash:
    @pytest.mark.parametrize("cmd", [
        f"cat project-history/council/2026-11/{OPEN}.ndjson",
        "grep -r claim project-history/council",
        "rg claim project-history/council/",
        "jq . project-history/council/2026-11/*.ndjson",
        "python3 -c \"print(open('project-history/council/2026-11/x.ndjson').read())\"",
        "git show HEAD:project-history/council/2026-11/x.ndjson"])
    def test_read_verbs_denied(self, tmp_path, cmd):
        _tree(tmp_path)
        assert _d(tmp_path, "Bash", command=cmd)

    @pytest.mark.parametrize("cmd", [
        "python mcp/noctusai/cli.py --council-ledger blind_view",
        "git add project-history/council/2026-11/x.ndjson",
        "ls project-history/council/2026-11",
        "cat products/core/x.py"])
    def test_tool_and_non_reads_pass(self, tmp_path, cmd):
        _tree(tmp_path)
        assert _d(tmp_path, "Bash", command=cmd) is None

    def test_verdicted_file_in_bash_allowed(self, tmp_path):
        _tree(tmp_path)
        assert _d(tmp_path, "Bash", command=f"cat project-history/council/2026-11/{DONE}.ndjson") is None


def _run(payload, mode=None, log=None):
    env = {**os.environ, "NOCTUS_GUARD_EVENT_LOG": str(log)}
    env.pop("NOC_COUNCIL_READ_MODE", None)
    if mode:
        env["NOC_COUNCIL_READ_MODE"] = mode
    p = subprocess.run([sys.executable, str(HOOK)], input=payload, capture_output=True, text=True, timeout=30,
                       cwd=str(REPO_ROOT), env=env)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else None)


@pytest.fixture
def open_session_in_repo():
    """The hook reads the REAL tree it lives in: plant (and always remove) one open session file there."""
    d = REPO_ROOT / "project-history/council/2099-01"
    f = d / f"{OPEN}.ndjson"
    d.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"record": "session", "session_id": OPEN}) + "\n")
    try:
        yield f
    finally:
        f.unlink(missing_ok=True)
        try:
            d.rmdir()
        except OSError:
            pass


def _read(path):
    return json.dumps({"tool_name": "Read", "cwd": str(REPO_ROOT), "tool_input": {"file_path": path}})


def test_hook_enforce_denies_and_logs(tmp_path, open_session_in_repo):
    log = tmp_path / "ev.ndjson"
    code, out = _run(_read(str(open_session_in_repo)), mode="enforce", log=log)
    assert code == 0
    assert out["hookSpecificOutput"]["permissionDecisionReason"].startswith("[noc-guard:council-read] ")
    assert json.loads(log.read_text().splitlines()[-1])["outcome"] == "deny"


def test_hook_default_is_shadow_warns_and_allows(tmp_path, open_session_in_repo):
    log = tmp_path / "ev.ndjson"
    assert _run(_read(str(open_session_in_repo)), log=log) == (0, None)
    row = json.loads(log.read_text().splitlines()[-1])
    assert row["guard"] == "council-read" and row["outcome"] == "warn" and row["kind"] == "guard"


def test_hook_allows_unrelated_silently(tmp_path):
    log = tmp_path / "ev.ndjson"
    assert _run(_read(str(REPO_ROOT / "CLAUDE.md")), log=log) == (0, None)
    assert not log.exists()


@pytest.mark.parametrize("stdin", ["{nope", "", "[]"])
def test_hook_bad_stdin_fails_closed(tmp_path, stdin):
    code, out = _run(stdin, log=tmp_path / "ev.ndjson")
    assert code == 0 and out["hookSpecificOutput"]["permissionDecisionReason"].startswith("[noc-guard:council-read] ")
