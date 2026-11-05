"""`check_workflow_job_timeouts` — every workflow job declares a bounded
`timeout-minutes`; apt steps carry a step timeout (2026-11-05 merge-queue hang).

→ KB § PATTERNS/devops/merge-queue.md
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_workflow_job_timeouts  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def _repo(tmp_path: Path, name: str, body: str) -> Path:
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True)
    (d / name).write_text(body)
    return tmp_path


def test_clean_job_passes(tmp_path):
    r = _repo(tmp_path, "a.yml", "jobs:\n  x:\n    runs-on: ubuntu-latest\n    timeout-minutes: 20\n    steps:\n      - run: echo hi\n")
    assert check_workflow_job_timeouts(r) == []


def test_missing_timeout_flagged(tmp_path):
    r = _repo(tmp_path, "a.yml", "jobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n")
    out = check_workflow_job_timeouts(r)
    assert len(out) == 1 and "no `timeout-minutes`" in out[0]["issue"] and out[0]["severity"] == "high"


def test_over_ceiling_flagged(tmp_path):
    r = _repo(tmp_path, "a.yml", "jobs:\n  x:\n    runs-on: u\n    timeout-minutes: 360\n    steps:\n      - run: echo\n")
    assert "exceeds the ceiling" in check_workflow_job_timeouts(r)[0]["issue"]


def test_merge_queue_drain_exempt_to_360(tmp_path):
    r = _repo(tmp_path, "merge-queue.yml", "jobs:\n  drain:\n    runs-on: u\n    timeout-minutes: 350\n    steps:\n      - run: echo\n")
    assert check_workflow_job_timeouts(r) == []


def test_reusable_call_skipped(tmp_path):
    r = _repo(tmp_path, "a.yml", "jobs:\n  x:\n    uses: ./.github/workflows/b.yml\n")
    assert check_workflow_job_timeouts(r) == []


def test_apt_step_without_timeout_flagged(tmp_path):
    body = "jobs:\n  x:\n    runs-on: u\n    timeout-minutes: 20\n    steps:\n      - name: deps\n        run: sudo apt-get install -y foo\n"
    out = check_workflow_job_timeouts(_repo(tmp_path, "a.yml", body))
    assert len(out) == 1 and "apt" in out[0]["issue"]


def test_apt_step_with_timeout_passes(tmp_path):
    body = "jobs:\n  x:\n    runs-on: u\n    timeout-minutes: 20\n    steps:\n      - name: deps\n        timeout-minutes: 10\n        run: sudo apt-get install -y foo\n"
    assert check_workflow_job_timeouts(_repo(tmp_path, "a.yml", body)) == []


def test_live_repo_is_clean():
    assert check_workflow_job_timeouts(REPO) == []
