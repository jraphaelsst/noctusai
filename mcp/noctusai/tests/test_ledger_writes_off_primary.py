"""Ledger tools never strand rows in the shared PRIMARY checkout (2026-11-15 steward finding).

Real git throughout (a fake "primary" clone of a bare origin, a real linked worktree); no patching of our own code.
Construction leg: `findings_ledger` append/update ship through `_ledger_store` and leave every working tree clean.
Backstop leg: a tree-writing ledger/registry tool aimed at the primary-on-`dev` refuses and names `ledger_store`.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import _primary_ledger_guard as pg  # noqa: E402
from tools.noctus.dev import findings_ledger as fl  # noqa: E402
from tools.noctus.dev import gate_alignment as ga  # noqa: E402

LEDGER = "gate-walls"
STORE_FILE = "findings-gate-walls.ndjson"
TREE_REL = "project-history/gate-alignment/findings.ndjson"


def g(cwd, *a):
    r = subprocess.run(["git", *a], cwd=str(cwd), capture_output=True, text=True)
    assert r.returncode == 0, f"git {a}: {r.stderr}"
    return r.stdout


@pytest.fixture
def primary(ledger_repo):
    """The fake primary: the clone, on `dev`, with a feat worktree beside it."""
    bare, clone, show = ledger_repo
    g(clone, "checkout", "-q", "-B", "dev")
    wt = clone.parent / "wt"
    g(clone, "worktree", "add", "-q", "-b", "feat/x", str(wt), "dev")
    return clone, wt, show


@pytest.fixture
def guard_log(tmp_path, monkeypatch):
    log = tmp_path / "guard-events.ndjson"
    monkeypatch.setenv("NOCTUS_GUARD_EVENT_LOG", str(log))
    return log


# ── construction leg: row writes ship off-primary ──────────────────────────────
def test_append_ships_to_store_and_leaves_primary_clean(primary):
    clone, _wt, show = primary
    out = fl.append(LEDGER, clone, scope="tooling-engineer", target="t1", found_by="x", severity="medium", kind="wall")
    assert out["ok"] and out["store"]["pushed"] is True
    rows = [json.loads(x) for x in show(STORE_FILE).splitlines()]
    assert [r["id"] for r in rows] == [out["id"]]
    assert g(clone, "status", "--porcelain") == ""  # nothing written into the primary tree
    assert not (clone / TREE_REL).exists()
    assert fl.load(fl.get(LEDGER), clone)[rows[0]["key"]]["status"] == "open"


def test_update_carries_a_tree_only_row_into_the_store(primary):
    clone, _wt, show = primary
    lt = fl.get(LEDGER)
    row = fl._row(lt, "manual:s:old", {"scope": "s", "target": "old", "kind": "wall"}, "manual", "x")
    (clone / TREE_REL).parent.mkdir(parents=True)
    (clone / TREE_REL).write_text(json.dumps(row, sort_keys=True) + "\n")
    g(clone, "add", "-A")
    g(clone, "commit", "-qm", "tree copy")
    landed = g(clone, "rev-parse", "HEAD").strip()  # on origin/dev: `fixed` is only written for such a sha
    out = fl.update(LEDGER, clone, id=row["id"], status="fixed", detail=landed)
    assert out["ok"] and out["store"]["pushed"] is True
    stored = [json.loads(x) for x in show(STORE_FILE).splitlines()]
    assert stored[0]["status"] == "fixed" and stored[0]["status_detail"] == landed
    assert fl.load(lt, clone)["manual:s:old"]["status"] == "fixed"  # the store overrides the tree copy
    assert g(clone, "status", "--porcelain") == ""


def test_duplicate_append_is_refused_not_pushed(primary):
    clone, _wt, show = primary
    assert fl.append(LEDGER, clone, scope="s", target="t", found_by="x", kind="wall")["ok"]
    again = fl.append(LEDGER, clone, scope="s", target="t", found_by="x", kind="wall")
    assert again["ok"] is False and "already exists" in again["error"]
    assert len(show(STORE_FILE).splitlines()) == 1


def test_unpublishable_store_reports_not_applied(primary):
    clone, _wt, _show = primary
    g(clone, "remote", "set-url", "origin", str(clone.parent / "nowhere.git"))
    out = fl.append(LEDGER, clone, scope="s", target="t", found_by="x", kind="wall")
    assert out["ok"] is False and "NOT applied" in out["error"]


# ── backstop leg: tree writes aimed at the shared primary refuse ───────────────
def test_primary_on_shared_branch_is_detected(primary):
    clone, wt, _ = primary
    assert pg.is_shared_primary(clone) == (True, "dev")
    assert pg.is_shared_primary(wt) == (False, "")        # a linked worktree ships with its own branch
    g(clone, "checkout", "-q", "-b", "feat/y")
    assert pg.is_shared_primary(clone) == (False, "feat/y")  # primary on a feature branch is not the shared case


def test_non_git_dir_is_not_the_primary(tmp_path):
    assert pg.is_shared_primary(tmp_path) == (False, "")
    pg.ensure_not_shared_primary(tmp_path, "t")  # no raise


def test_guard_refusal_names_ledger_store_and_records_an_event(primary, guard_log):
    clone, _wt, _ = primary
    with pytest.raises(pg.PrimaryLedgerWriteRefused) as exc:
        pg.ensure_not_shared_primary(clone, "findings_ledger.save")
    assert "[noc-guard:ledger-primary-write]" in str(exc.value) and "ledger_store" in str(exc.value)
    ev = [json.loads(x) for x in guard_log.read_text().splitlines()]
    assert ev and ev[-1]["outcome"] == "deny" and ev[-1]["guard"] == pg.GATE


def test_reconcile_and_save_refuse_on_the_primary_but_work_in_a_worktree(primary, monkeypatch, tmp_path, guard_log):
    clone, wt, _ = primary
    monkeypatch.setenv(fl.ls.ENV_MODE, fl.ls.MODE_FAKE)  # tree-writing path (what tests and legacy callers use)
    lt = fl.get(LEDGER)
    refused = fl.reconcile(LEDGER, clone)
    assert refused["ok"] is False and "ledger_store" in refused["error"]
    with pytest.raises(pg.PrimaryLedgerWriteRefused):
        fl.save(lt, {}, clone)
    assert not (clone / TREE_REL).exists()
    fl.save(lt, {}, wt)
    assert (wt / TREE_REL).exists()


def test_materialize_writes_the_merged_rows_into_a_worktree(primary):
    clone, wt, _show = primary
    out = fl.append(LEDGER, clone, scope="s", target="m", found_by="x", kind="wall")
    mat = fl.materialize(LEDGER, wt)
    assert mat["ok"] and mat["rows"] == 1
    assert out["id"] in (wt / TREE_REL).read_text()
    assert out["id"] in (wt / "project-history/gate-alignment/FINDINGS.md").read_text()
    refused = fl.materialize(LEDGER, clone)
    assert refused["ok"] is False and "ledger_store" in refused["error"]


def test_gate_alignment_writers_refuse_on_the_primary(primary, guard_log):
    clone, wt, _ = primary
    with pytest.raises(pg.PrimaryLedgerWriteRefused):
        ga.declare_gate("g1", "KB § PATTERNS/common/x.md", "tooling-engineer", root=clone)
    with pytest.raises(pg.PrimaryLedgerWriteRefused):
        ga.refresh_baseline(clone)
