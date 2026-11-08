"""Merge driver for gate-alignment-inventory.json: pure logic + end-to-end git merge."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.noctus.dev.gate_alignment import merge_inventory  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
HOOKS = REPO / "scripts" / "hooks"
INV = "KNOWLEDGE-BASE/CONTEXT/PATTERNS/common/gate-alignment-inventory.json"


def _dec(i, text, gate="g"):
    return {"id": i, "decision": text, "gate": gate}


def _inv(gates=(), decisions=(), **extra):
    return json.dumps({"measured_over": "m", **extra, "gates": {g: {"severity": s} for g, s in gates},
                       "decisions": list(decisions)}, indent=1, ensure_ascii=False) + "\n"


BASE = _inv([("a", "x")], [_dec("D1", "one")])


def test_same_new_id_different_decisions_renumbered():
    ours = _inv([("a", "x")], [_dec("D1", "one"), _dec("D2", "ours", "go")])
    theirs = _inv([("a", "x")], [_dec("D1", "one"), _dec("D2", "theirs", "gt")])
    text, conflicted, _ = merge_inventory(BASE, ours, theirs)
    ids = [(d["id"], d["decision"]) for d in json.loads(text)["decisions"]]
    assert not conflicted
    assert ids == [("D1", "one"), ("D2", "ours"), ("D3", "theirs")]


def test_different_gates_union_sorted():
    ours = _inv([("a", "x"), ("z", "x")], [_dec("D1", "one")])
    theirs = _inv([("a", "x"), ("m", "x")], [_dec("D1", "one")])
    text, conflicted, _ = merge_inventory(BASE, ours, theirs)
    assert not conflicted
    assert list(json.loads(text)["gates"]) == ["a", "m", "z"]


def test_same_gate_edited_differently_conflicts():
    ours = _inv([("a", "ours")], [_dec("D1", "one")])
    theirs = _inv([("a", "theirs")], [_dec("D1", "one")])
    _, conflicted, notes = merge_inventory(BASE, ours, theirs)
    assert conflicted and "gate 'a'" in notes[0]


def test_one_sided_gate_edit_taken():
    theirs = _inv([("a", "new")], [_dec("D1", "one")])
    text, conflicted, _ = merge_inventory(BASE, BASE, theirs)
    assert not conflicted and json.loads(text)["gates"]["a"]["severity"] == "new"


def test_identical_decision_kept_once_even_with_different_ids():
    ours = _inv([("a", "x")], [_dec("D1", "one"), _dec("D2", "same")])
    theirs = _inv([("a", "x")], [_dec("D1", "one"), _dec("D3", "same")])
    text, _, notes = merge_inventory(BASE, ours, theirs)
    assert [d["id"] for d in json.loads(text)["decisions"]] == ["D1", "D2"]
    assert any("dedup" in n for n in notes)


def test_same_gate_and_decision_text_deduped_despite_other_fields():
    o = {**_dec("D2", "same"), "home": "a"}
    t = {**_dec("D2", "same"), "home": "b"}
    text, _, _ = merge_inventory(BASE, _inv(decisions=[_dec("D1", "one"), o]),
                                 _inv(decisions=[_dec("D1", "one"), t]))
    assert len(json.loads(text)["decisions"]) == 2


def test_other_top_level_keys_three_way():
    ours = _inv(decisions=[_dec("D1", "one")], measured_over="m")
    theirs = json.dumps({**json.loads(_inv([("a", "x")], [_dec("D1", "one")])), "measured_over": "n"},
                        indent=1, ensure_ascii=False) + "\n"
    text, conflicted, _ = merge_inventory(BASE, BASE, theirs)
    assert not conflicted and json.loads(text)["measured_over"] == "n"
    _, conflicted, _ = merge_inventory(BASE, theirs.replace('"n"', '"p"'), theirs)
    assert conflicted


def test_format_byte_stable_with_real_inventory():
    real = (REPO / INV).read_text(encoding="utf-8")
    text, conflicted, _ = merge_inventory(real, real, real)
    assert text == real and not conflicted


# ── end-to-end ────────────────────────────────────────────────────────────
def _git(cwd, *a, check=True):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          cwd=cwd, check=check, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHON", sys.executable)
    root = tmp_path / "r"
    (root / "scripts/hooks").mkdir(parents=True)
    (root / "mcp/noctusai/tools/noctus/dev").mkdir(parents=True)
    for f in ("merge-kb-counts.sh", "merge-lgpd-warnings.sh", "merge-gate-inventory.sh", "register-merge-drivers.sh"):
        shutil.copy(HOOKS / f, root / "scripts/hooks" / f)
    # thin cli: the real flag handler needs the whole toolkit; exercise the real pure function
    (root / "mcp/noctusai/cli.py").write_text(
        "import sys\nsys.path.insert(0, %r)\n"
        "from tools.noctus.dev.gate_alignment import merge_inventory\n"
        "a = sys.argv[1:]\n"
        "t = [open(f).read() for f in a[a.index('--merge-gate-inventory')+1:][:3]]\n"
        "m, c, _ = merge_inventory(*t)\nopen(a[a.index('--out')+1], 'w').write(m)\nsys.exit(10 if c else 0)\n"
        % str(REPO / "mcp/noctusai"))
    (root / ".gitattributes").write_text(f"{INV} merge=gate-inventory\n")
    (root / INV).parent.mkdir(parents=True)
    (root / INV).write_text(BASE)
    _git(root, "init", "-q", "-b", "dev")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    return root


def _branch(root, name, inv):
    _git(root, "checkout", "-q", "-b", name, "dev")
    (root / INV).write_text(inv)
    _git(root, "commit", "-qam", name)


def _register(root):
    subprocess.run(["bash", str(root / "scripts/hooks/register-merge-drivers.sh"), str(root)],
                   check=True, capture_output=True, env={**os.environ, "PYTHON": sys.executable})


def _setup(repo, inv_a, inv_b):
    _branch(repo, "a", inv_a)
    _branch(repo, "b", inv_b)
    _git(repo, "checkout", "-q", "a")


A = _inv([("a", "x"), ("n1", "x")], [_dec("D1", "one"), _dec("D2", "from a", "n1")])
B = _inv([("a", "x"), ("n0", "x")], [_dec("D1", "one"), _dec("D2", "from b", "n0")])


def test_unregistered_driver_conflicts(repo):
    _setup(repo, A, B)
    assert _git(repo, "merge", "--no-edit", "b", check=False).returncode != 0


def test_e2e_merge_renumbers_and_unions(repo):
    _register(repo)
    _setup(repo, A, B)
    r = _git(repo, "merge", "--no-edit", "b", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    d = json.loads((repo / INV).read_text())
    assert list(d["gates"]) == ["a", "n0", "n1"]
    assert [(x["id"], x["decision"]) for x in d["decisions"]] == [
        ("D1", "one"), ("D2", "from a"), ("D3", "from b")]


def test_e2e_real_gate_conflict_surfaces(repo):
    _register(repo)
    _setup(repo, _inv([("a", "ours")], [_dec("D1", "one")]), _inv([("a", "theirs")], [_dec("D1", "one")]))
    assert _git(repo, "merge", "--no-edit", "b", check=False).returncode != 0
