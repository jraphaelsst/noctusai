"""Scoped branch verdicts + scheduled full suite (2026-11-17, owner-approved).

Pins the test.yml contract: `scope` input defaults to `changed`, a schedule on dev runs the full suite every 6h and names
the red range, the run title carries `[scope=full|changed]` (what release bless reads, ONE `gh run list`), and a
scope=changed dispatch diffs against base / merge-base(origin/dev) while shared surfaces still escalate (ci_scope).
Plus the pure helpers in ci_full_green.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import ci_full_green as fg  # noqa: E402
from tools.noctus.dev import ci_scope  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
TEXT = (REPO / ".github/workflows/test.yml").read_text(encoding="utf-8")
WF = yaml.safe_load(TEXT)
ON = WF.get(True) or WF["on"]


def test_scope_input_defaults_to_changed_with_the_two_choices():
    scope = ON["workflow_dispatch"]["inputs"]["scope"]
    assert scope["default"] == "changed" and scope["options"] == ["changed", "full"]


def test_a_six_hourly_schedule_runs_on_dev_by_default_branch():
    assert ON["schedule"] == [{"cron": "0 */6 * * *"}]


def test_run_name_carries_the_scope_mark_release_reads():
    rn = WF["run-name"]
    # the mark release reads is `[scope=full]`; the run-name renders it from an expression ending in 'full'|'changed'
    assert fg.FULL_MARK == "[scope=full]" and "[scope=${{" in rn and rn.rstrip().endswith("}}]")
    assert "'full'" in rn and "'changed'" in rn
    assert "'full'" in WF["run-name"] and "inputs.scope" in WF["run-name"]


def test_classify_only_forces_full_for_schedule_scope_full_or_release_refs():
    changes = TEXT[TEXT.index("\n  changes:\n"):TEXT.index("\n  product-backend-tests:\n")]
    head = changes[changes.index("# Full suite when:"):changes.index('if [ "${{ github.event_name }}" = "pull_request" ]')]
    assert 'event_name }}" = "schedule"' in head and 'inputs.scope }}" = "full"' in head
    # a bare workflow_dispatch is no longer enough to go full
    assert 'event_name }}" = "workflow_dispatch" ]; then' not in head
    assert "merge-base origin/dev" in changes and "github.event.inputs.base" in changes


def test_the_report_job_waits_on_every_job_and_uses_the_actions_token_only():
    job = WF["jobs"]["scheduled-full-report"]
    others = set(WF["jobs"]) - {"scheduled-full-report"}
    assert set(job["needs"]) == others, "a job missing from needs makes a red it owns invisible to the report"
    assert "schedule" in job["if"] and "failure" in job["if"]
    text = yaml.dump(job)
    assert "github.token" in text and "secrets." not in text
    assert text.count("gh run list") == 2, "the report is a constant-cost lookup, not a loop over runs"


def test_shared_surfaces_escalate_a_scoped_diff_to_every_product():
    for p in ("seed/framework/a.py", ".github/workflows/test.yml", "scripts/ci/x.py",
              "package-lock.json", "requirements.txt"):
        assert ci_scope.classify([p, "products/core/a.py"]).shared_changed, p
    only = ci_scope.classify(["products/core/a.py"])
    assert not only.shared_changed and only.changed_products == ("core",)


def test_full_title_detection_and_last_full_green():
    runs = [{"displayTitle": "Tests & Build [scope=changed]", "headSha": "a"},
            {"displayTitle": "Tests & Build [scope=full]", "headSha": "b"},
            {"displayTitle": "Tests & Build [scope=full]", "headSha": "c"}]
    assert not fg.is_full_title(runs[0]["displayTitle"]) and fg.is_full_title(runs[1]["displayTitle"])
    assert fg.last_full_green(runs, lambda a, b: True, "H") == "b"
    assert fg.last_full_green(runs, lambda a, b: a == "c", "H") == "c"
    assert fg.last_full_green(runs[:1], lambda a, b: True, "H") is None
