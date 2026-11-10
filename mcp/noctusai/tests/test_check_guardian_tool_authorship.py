"""check_guardian_tool_authorship: the lease holder never stages steward tooling.

Real lease files in tmp dirs via StewardStore; session/clock/root injected.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    GUARDIAN_PROTECTED_TOOL_FILES,
    check_guardian_tool_authorship,
)
from tools.noctus.dev.release_steward import StewardStore  # noqa: E402

RS, TB = GUARDIAN_PROTECTED_TOOL_FILES


def _claim(root: Path, sid: str = "sess-guardian-1") -> None:
    res = StewardStore(root).claim(sid, name="guardian", reason="test")
    assert res.get("ok"), res


def _check(root, staged, sid="sess-guardian-1", now=None, events=None):
    ev = events if events is not None else root / "events.ndjson"
    os.environ["NOCTUS_GUARD_EVENT_LOG"] = str(ev)
    try:
        return check_guardian_tool_authorship(staged=staged, session_id=sid, lease_root=root, now=now)
    finally:
        os.environ.pop("NOCTUS_GUARD_EVENT_LOG", None)


def _events(root: Path) -> list[dict]:
    p = root / "events.ndjson"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


class TestCheckGuardianToolAuthorship:
    def test_holder_staging_release_steward_is_refused(self, tmp_path):
        _claim(tmp_path)
        issues = _check(tmp_path, [RS, "README.md"])
        assert len(issues) == 1 and issues[0]["severity"] == "high"
        assert RS in issues[0]["file"] and "guardian" in issues[0]["issue"]
        assert "tooling branch steward" in issues[0]["issue"]
        assert any(e.get("outcome") == "deny" for e in _events(tmp_path))


    def test_holder_staging_task_branch_is_refused(self, tmp_path):
        _claim(tmp_path)
        assert len(_check(tmp_path, [TB])) == 1


    def test_holder_staging_other_files_passes(self, tmp_path):
        _claim(tmp_path)
        assert _check(tmp_path, ["mcp/noctusai/tools/noctus/dev/compliance.py", "x.md"]) == []


    def test_non_holder_passes(self, tmp_path):
        _claim(tmp_path)
        assert _check(tmp_path, [RS, TB], sid="some-other-session") == []


    def test_no_lease_file_passes_and_records_why(self, tmp_path):
        assert _check(tmp_path, [RS]) == []
        ev = _events(tmp_path)
        assert ev and "no-lease" in json.dumps(ev[-1])


    def test_expired_lease_is_not_a_holder(self, tmp_path):
        _claim(tmp_path)
        later = time.time() + 10 * 24 * 3600
        assert _check(tmp_path, [RS], now=later) == []
