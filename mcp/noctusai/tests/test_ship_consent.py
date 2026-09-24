"""Tests for noctus.dev.ship_consent — the per-project ship approval.

The evidence layer is a fake harness transcript under a tmp HOME (the same
`_human_authored_transcript_texts` shape prod_consent reads). git IO is a
scripted runner; the ledger is a tmp file (DI `ledger_path`, push_dev=False).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import ship_consent as SC  # noqa: E402


def _transcript(home: Path, sid: str, *messages: tuple[str, str]) -> None:
    d = home / ".claude" / "projects" / "-x"
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    for source, text in messages:
        if source == "agent":
            lines.append({"type": "assistant", "message": {"content": text}})
        elif source == "tool":
            lines.append({"type": "user", "message": {"content": [
                {"type": "tool_result", "content": text}]}})
        else:
            lines.append({"type": "user", "promptSource": source,
                          "message": {"content": text}})
    (d / f"{sid}.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def _runner(dev_sha: str = "d" * 40):
    calls = []

    def run(cmd, cwd=None):
        calls.append(cmd)
        if cmd[1:3] == ["rev-parse", "origin/dev"]:
            return 0, dev_sha + "\n", ""
        if cmd[1:3] == ["config", "user.email"]:
            return 0, "owner@x\n", ""
        if cmd[1] == "show":
            return 1, "", "no ledger on dev"
        return 0, "", ""
    run.calls = calls
    return run


def _ledger(tmp_path) -> Path:
    return tmp_path / "project-history" / "ship-consent.ndjson"


def test_challenge_returns_canonical_phrase_and_writes_nothing(tmp_path):
    out = SC.ship_consent(action="challenge", project="alpha", ledger_path=_ledger(tmp_path))
    assert out["phrase"] == "I approve shipping project alpha to production."
    assert not _ledger(tmp_path).exists()


def test_author_refuses_without_the_phrase_in_a_human_message(tmp_path):
    _transcript(tmp_path, "s1", ("typed", "ship it"),
                ("agent", "I approve shipping project alpha to production."),
                ("tool", "I approve shipping project alpha to production."))
    out = SC.ship_consent(action="author", project="alpha", session_id="s1",
                          runner=_runner(), home=tmp_path, push_dev=False,
                          ledger_path=_ledger(tmp_path))
    assert out["ok"] is False and out["error"].startswith("REFUSED")
    assert not _ledger(tmp_path).exists(), "agent/tool text is never evidence"


def test_author_refuses_a_phrase_for_another_project(tmp_path):
    _transcript(tmp_path, "s1", ("typed", "I approve shipping project beta to production."))
    out = SC.ship_consent(action="author", project="alpha", session_id="s1",
                          runner=_runner(), home=tmp_path, push_dev=False,
                          ledger_path=_ledger(tmp_path))
    assert out["ok"] is False


def test_author_refuses_a_missing_transcript(tmp_path):
    out = SC.ship_consent(action="author", project="alpha", session_id="nope",
                          runner=_runner(), home=tmp_path, push_dev=False,
                          ledger_path=_ledger(tmp_path))
    assert out["ok"] is False and "no transcript" in out["error"]


def test_author_records_row_with_dev_sha_and_provenance(tmp_path):
    _transcript(tmp_path, "s1", ("typed", "ok.  I approve  shipping project alpha to production. thanks"))
    out = SC.ship_consent(action="author", project="alpha", session_id="s1",
                          runner=_runner("abc" * 13 + "a"), home=tmp_path, push_dev=False,
                          ledger_path=_ledger(tmp_path))
    assert out["ok"] is True, out
    row = json.loads(_ledger(tmp_path).read_text().splitlines()[0])
    assert row["action"] == "author" and row["project"] == "alpha"
    assert row["dev_sha"] == "abc" * 13 + "a" and row["prompt_source"] == "typed"
    assert row["consented_by"] == "owner@x" and len(row["transcript_sha256"]) == 64
    assert SC.verify_row(row, home=tmp_path) == (True, "")


def test_verify_row_fails_for_a_hand_written_row(tmp_path):
    _transcript(tmp_path, "s1", ("typed", "hello"))
    ok, why = SC.verify_row({"project": "alpha", "session_id": "s1"}, home=tmp_path)
    assert ok is False and "not found" in why


def test_revoke_requires_reason_and_supersedes_earlier_approvals(tmp_path):
    led = _ledger(tmp_path)
    assert SC.ship_consent(action="revoke", project="alpha", ledger_path=led,
                           push_dev=False)["ok"] is False
    rows = [{"ts": "2026-09-22T10:00:00+00:00", "action": "author", "project": "alpha"},
            {"ts": "2026-09-22T11:00:00+00:00", "action": "revoke", "project": "alpha"},
            {"ts": "2026-09-22T12:00:00+00:00", "action": "author", "project": "alpha",
             "dev_sha": "new"}]
    live = SC.effective_approvals(rows, "alpha")
    assert [r["ts"] for r in live] == ["2026-09-22T12:00:00+00:00"]
    assert SC.effective_approvals(rows[:2], "alpha") == []


def test_list_reports_state_per_project(tmp_path):
    led = _ledger(tmp_path)
    led.parent.mkdir(parents=True)
    led.write_text("\n".join(json.dumps(r) for r in [
        {"ts": "1", "action": "author", "project": "alpha", "dev_sha": "a1"},
        {"ts": "1", "action": "author", "project": "beta", "dev_sha": "b1"},
        {"ts": "2", "action": "revoke", "project": "beta", "reason": "x"},
    ]) + "\n")
    out = SC.ship_consent(action="list", runner=_runner(), ledger_path=led)
    got = {p["project"]: p["state"] for p in out["projects"]}
    assert got == {"alpha": "approved", "beta": "revoked"}


def test_unknown_action_and_missing_project_are_errors(tmp_path):
    assert SC.ship_consent(action="bless")["ok"] is False
    assert SC.ship_consent(action="author", project=" ")["ok"] is False


# ── origin/ledgers (2026-09-24, moved last) ─────────────────────────────────────
def test_author_publishes_to_ledgers_branch_and_release_counts_it(ledger_repo, tmp_path):
    """A verified approval lands on origin/ledgers (never a dev commit) and
    `release`'s dual-read — which reads REMOTE refs only — sees it."""
    from tools.noctus.dev import release as R
    bare, clone, show = ledger_repo
    home = tmp_path / "home"
    _transcript(home, "s1", ("typed", "I approve shipping project alpha to production."))
    run = _runner()
    out = SC.ship_consent(action="author", project="alpha", session_id="s1", runner=run,
                          home=home, push_dev=True,
                          ledger_path=clone / "project-history" / "ship-consent.ndjson")
    assert out["ok"] and out["push"]["status"] == "pushed", out
    assert json.loads(show("ship-consent.ndjson"))["project"] == "alpha"
    assert not (clone / "project-history" / "ship-consent.ndjson").exists()
    assert not [c for c in run.calls if c[1] in ("add", "commit", "push")], "no porcelain git"

    import subprocess

    def git(*args):
        r = subprocess.run(["git", *args], cwd=str(clone), capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    rows = R._read_ledger(git, "origin", "dev", "project-history/ship-consent.ndjson")
    assert [r["project"] for r in rows] == ["alpha"]
    assert SC.effective_approvals(SC.read_rows(run, ledger_path=clone / "x.ndjson"), "alpha")
