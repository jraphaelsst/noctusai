"""Julia's mistakes ledger: the repo file is consistent and the reconcile hook lets the eval runner decide open vs closed."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_DIR = Path(__file__).resolve().parents[2] / "projects" / "julia-v2" / "ledger"
_spec = importlib.util.spec_from_file_location("julia_reconcilia", _DIR / "reconcilia.py")
rec = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rec)


def _row(status, caso="mec-x", passk=None):
    return {"id": "JL-999", "atribuicao": "STRUCTURAL", "status": status, "caso_eval": caso, "passk": passk}


def test_the_ledger_in_the_repo_agrees_with_its_own_latest_runs():
    assert rec.divergencias(rec.ler(_DIR / "julia-mistakes.ndjson")) == []


def test_a_passing_case_closes_an_open_row_and_a_failing_one_reopens_a_fixed_row():
    ok = {"mec-x": {"k": 3, "aprovadas": 3, "passou": True}}
    ko = {"mec-x": {"k": 3, "aprovadas": 2, "passou": False}}
    [m] = rec.reconciliar([_row("open")], ok, run="r1", hash_="h", sha="abc")
    assert m["para"] == "fixed abc" and m["passk"]["aprovadas"] == 3
    [m] = rec.reconciliar([_row("fixed abc")], ko, run="r2", hash_="h", sha=None)
    assert m["para"] == "open"
    [m] = rec.reconciliar([_row("accepted porque sim")], ko, run="r3", hash_=None, sha=None) or [None]
    assert m is None  # accepted rows are the owner's call


def test_a_status_that_disagrees_with_the_latest_run_fails_the_check():
    fixed_but_red = _row("fixed abc", passk={"k": 3, "aprovadas": 2})
    open_but_green = _row("open", passk={"k": 3, "aprovadas": 3})
    assert len(rec.divergencias([fixed_but_red, open_but_green])) == 2
    assert rec.divergencias([_row("fixed abc", caso=None)])  # a fix needs the case that reproduces it
