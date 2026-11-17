"""A findings-ledger row can only say `fixed` for a commit that is on origin/dev (2026-11-16, GW-a02d4a1e).

Real git throughout (a bare origin + clone via the `ledger_repo` fixture, a real unlanded feature branch); nothing of
ours is patched. Construction leg: `update`/`append` write `in-progress` + fix_sha/fix_branch for an off-dev sha, and
`flip_landed` closes it when the sha lands. Backstop leg: the keeper flags a hand-edited `fixed` row.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import findings_ledger as fl  # noqa: E402
from tools.noctus.dev.compliance import FIXED_ON_DEV_BASELINE_REL, check_findings_fixed_on_dev  # noqa: E402

LEDGER = "gate-walls"
TREE_REL = "project-history/gate-alignment/findings.ndjson"


def g(cwd, *a):
    r = subprocess.run(["git", *a], cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"git {a}: {r.stderr}"
    return r.stdout.strip()


@pytest.fixture
def repo(ledger_repo, tmp_path, monkeypatch):
    """(clone, on_dev_sha, feat_sha): the clone sits on `dev`; `feat_sha` lives only on pushed branch feat/fix."""
    monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(tmp_path / "events.ndjson"))
    _bare, clone, _show = ledger_repo
    g(clone, "checkout", "-q", "-B", "dev")
    on_dev = g(clone, "rev-parse", "HEAD")
    g(clone, "checkout", "-q", "-b", "feat/fix")
    (clone / "fix.txt").write_text("the fix\n")
    g(clone, "add", "fix.txt")
    g(clone, "commit", "-qm", "the fix")
    feat = g(clone, "rev-parse", "HEAD")
    g(clone, "push", "-q", "origin", "feat/fix")
    g(clone, "checkout", "-q", "dev")
    g(clone, "fetch", "-q", "origin")
    return clone, on_dev, feat


def _open(clone, target="t1"):
    out = fl.append(LEDGER, clone, scope="tooling-engineer", target=target, found_by="x", kind="wall")
    assert out["ok"]
    return out["id"]


def _row(clone, fid):
    return next(r for r in fl.load(fl.get(LEDGER), clone).values() if r["id"] == fid)


def _events(tmp_path):
    p = tmp_path / "events.ndjson"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


class TestFixedMeansOnDev:
    def test_a_sha_on_dev_is_written_fixed(self, repo):
        clone, on_dev, _feat = repo
        fid = _open(clone)
        out = fl.update(LEDGER, clone, id=fid, status="fixed", detail=f"fixed in {on_dev[:9]}")
        assert out["ok"] and out["status"] == "fixed" and out["status_written"] == "fixed"
        r = _row(clone, fid)
        assert r["status"] == "fixed" and r["fix_sha"] == on_dev and r["closed_at"]

    def test_a_sha_off_dev_is_written_in_progress_with_the_branch_and_says_so(self, repo, tmp_path):
        clone, _on_dev, feat = repo
        fid = _open(clone)
        out = fl.update(LEDGER, clone, id=fid, status="fixed", detail=f"fixed, {feat[:9]}")
        assert out["ok"] is True and out["status_written"] == "in-progress"
        assert out["fix_branch"] == "feat/fix" and feat[:9] in out["reason"] and "feat/fix" in out["reason"]
        r = _row(clone, fid)
        assert r["status"] == "in-progress" and r["fix_sha"] == feat and r["fix_branch"] == "feat/fix" and not r["closed_at"]
        assert any(e.get("outcome") == "warn" and "downgraded" in (e.get("reason") or "") for e in _events(tmp_path))

    def test_the_explicit_fix_sha_argument_wins_over_detail_parsing(self, repo):
        clone, _on_dev, feat = repo
        fid = _open(clone)
        out = fl.update(LEDGER, clone, id=fid, status="fixed", detail="see the branch", fix_sha=feat)
        assert out["status_written"] == "in-progress" and _row(clone, fid)["fix_sha"] == feat

    def test_no_sha_at_all_is_refused_and_accepted_is_untouched(self, repo):
        clone, _on_dev, _feat = repo
        fid = _open(clone)
        out = fl.update(LEDGER, clone, id=fid, status="fixed", detail="just fixed it")
        assert out["ok"] is False and "needs its commit" in out["error"]
        assert _row(clone, fid)["status"] == "open"
        assert fl.update(LEDGER, clone, id=fid, status="accepted", detail="by design")["ok"]
        assert _row(clone, fid)["status"] == "accepted"

    def test_append_born_fixed_obeys_the_same_rule(self, repo):
        clone, _on_dev, feat = repo
        out = fl.append(LEDGER, clone, scope="s", target="born", found_by="x", kind="wall", status="fixed", detail=feat[:9])
        assert out["ok"] and out["status_written"] == "in-progress"
        assert fl.append(LEDGER, clone, scope="s", target="nosha", found_by="x", kind="wall", status="fixed", detail="done")["ok"] is False


class TestFlipOnLanding:
    def test_the_row_flips_to_fixed_once_its_sha_is_on_dev(self, repo, tmp_path):
        clone, _on_dev, feat = repo
        fid = _open(clone)
        fl.update(LEDGER, clone, id=fid, status="fixed", detail=feat[:9])
        assert fl.flip_landed(LEDGER, clone)["flipped"] == []  # not landed yet: nothing moves
        g(clone, "merge", "-q", "--ff-only", "feat/fix")
        g(clone, "push", "-q", "origin", "dev")
        g(clone, "fetch", "-q", "origin")
        out = fl.flip_landed(None, clone)
        assert out["ok"] and out["flipped"] == [fid]
        r = _row(clone, fid)
        assert r["status"] == "fixed" and feat[:9] in r["status_detail"] and "landed on origin/dev" in r["status_detail"]
        assert any(e.get("outcome") == "pass" for e in _events(tmp_path))
        assert fl.flip_landed(None, clone)["flipped"] == []  # idempotent

    def test_a_rebased_landing_counts_by_content(self, repo):
        clone, _on_dev, feat = repo
        fid = _open(clone)
        fl.update(LEDGER, clone, id=fid, status="fixed", detail=feat[:9])
        # dev moves, then the queue lands the same change under a NEW sha (cherry-pick = same patch)
        (clone / "other.txt").write_text("x\n")
        g(clone, "add", "other.txt")
        g(clone, "commit", "-qm", "other work")
        g(clone, "cherry-pick", feat)
        g(clone, "push", "-q", "origin", "dev")
        g(clone, "fetch", "-q", "origin")
        assert fl.flip_landed(None, clone)["flipped"] == [fid]


class TestFindingsFixedOnDev:
    def _hand_edit(self, clone, sha, detail=None):
        lt = fl.get(LEDGER)
        row = fl._row(lt, "manual:s:hand", {"scope": "s", "target": "hand", "kind": "wall"}, "manual", "x",
                      status="fixed", detail=detail if detail is not None else sha)
        (clone / TREE_REL).parent.mkdir(parents=True, exist_ok=True)
        (clone / TREE_REL).write_text(json.dumps(row, sort_keys=True) + "\n")
        return row["id"]

    def test_clean_when_every_fixed_row_is_on_dev(self, repo):
        clone, on_dev, _feat = repo
        self._hand_edit(clone, on_dev)
        assert check_findings_fixed_on_dev(repo_root=clone) == []

    def test_a_hand_edited_fixed_row_for_an_off_dev_sha_is_flagged(self, repo):
        clone, _on_dev, feat = repo
        rid = self._hand_edit(clone, feat)
        issues = check_findings_fixed_on_dev(repo_root=clone)
        assert len(issues) == 1 and issues[0]["severity"] == "high" and rid in issues[0]["issue"] and "not on origin/dev" in issues[0]["issue"]

    def test_a_fixed_row_naming_no_commit_is_flagged(self, repo):
        clone, _on_dev, _feat = repo
        self._hand_edit(clone, "", detail="done")
        assert "no commit named" in check_findings_fixed_on_dev(repo_root=clone)[0]["issue"]

    def test_baseline_tolerates_and_a_stale_entry_is_flagged(self, repo):
        clone, _on_dev, feat = repo
        rid = self._hand_edit(clone, feat)
        bl = clone / FIXED_ON_DEV_BASELINE_REL
        bl.parent.mkdir(parents=True, exist_ok=True)
        bl.write_text(json.dumps({"ids": [rid]}))
        assert check_findings_fixed_on_dev(repo_root=clone) == []
        bl.write_text(json.dumps({"ids": [rid, "GW-00000000"]}))
        assert "stale baseline entry GW-00000000" in check_findings_fixed_on_dev(repo_root=clone)[0]["issue"]

    def test_unmeasurable_without_an_origin_dev_ref_never_fails(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NOCTUS_LEDGER_STORE", "fake")
        g(tmp_path, "init", "-q")
        (tmp_path / TREE_REL).parent.mkdir(parents=True)
        lt = fl.get(LEDGER)
        row = fl._row(lt, "manual:s:x", {"scope": "s", "target": "x", "kind": "wall"}, "manual", "x", status="fixed", detail="abc1234")
        (tmp_path / TREE_REL).write_text(json.dumps(row, sort_keys=True) + "\n")
        assert check_findings_fixed_on_dev(repo_root=tmp_path) == []
