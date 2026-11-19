"""Colocated regression test for `check_refusal_classes_owned` (the gate-level cases live in
test_gate_alignment.TestUnownedKeeper; this pins the empty-event-log green path)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_refusal_classes_owned  # noqa: E402


class TestRefusalClassesOwned:
    def test_clean_case_no_issues(self, tmp_path):
        assert check_refusal_classes_owned(paths=[], repo_root=tmp_path, events=[]) == []

    def test_violation_flagged(self, tmp_path):
        import datetime as dt
        now = dt.datetime.now(dt.timezone.utc)
        evs = [{"gate": "g", "outcome": "deny", "class": "g:x", "session": f"s{i}",
                "ts": (now - dt.timedelta(days=i)).isoformat()} for i in (1, 2, 3)]
        (issue,) = check_refusal_classes_owned(paths=[], repo_root=tmp_path, events=evs)
        assert issue["severity"] == "high"
