"""`ledger-render` merge driver: two branches that each rewrite a GENERATED render merge cleanly, and the result is the
render of the MERGED source (real `git merge` in a temp repo, real cli)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.noctus.dev import findings_ledger as fl  # noqa: E402
from tools.noctus.dev import gate_alignment as ga  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
HOOKS = REPO / "scripts" / "hooks"
ENV = {**os.environ, "PYTHON": sys.executable}


def _git(cwd, *a, check=True):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=check,
                          capture_output=True, text=True, env=ENV)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for sub in ("scripts/hooks", "mcp"):
        (root / sub).mkdir(parents=True)
    for f in HOOKS.glob("*.sh"):
        shutil.copy(f, root / "scripts/hooks" / f.name)
    # the real toolkit through a symlink so cli.py resolves `tools.*` and the repo-relative KB
    (root / "mcp" / "noctusai").symlink_to(REPO / "mcp" / "noctusai")
    shutil.copy(REPO / ".gitattributes", root / ".gitattributes")
    (root / ".noctusai-workspace").write_text("")
    _git(root, "init", "-q", "-b", "main")
    return root


def _row(lt, key, scope="p", status="open"):
    return {"key": key, "id": fl._id(lt, key), "scope": scope, "target": key, "section": "scan", "severity": "high",
            "status": status, "status_detail": "", "found_by": "t", "found_at": "2026-11-14", "note": "n",
            **{e: "" for e in lt.extra}}


def _write_ledger(root: Path, lt, rows):
    (root / lt.path).parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda r: r["id"])
    (root / lt.path).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in ordered), encoding="utf-8")
    (root / lt.summary).write_text(fl.render_summary(lt, ordered), encoding="utf-8")


def _register(root):
    subprocess.run(["bash", str(root / "scripts/hooks/register-merge-drivers.sh"), str(root)], check=True,
                   capture_output=True, env=ENV)


def test_findings_render_is_regenerated_from_the_merged_ledger(tmp_path):
    lt = fl.get("gate-walls")
    root = _repo(tmp_path)
    base = [_row(lt, "w-base", scope="base-scope")]
    _write_ledger(root, lt, base)
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "base")
    _register(root)
    _git(root, "checkout", "-q", "-b", "theirs")
    _write_ledger(root, lt, base + [_row(lt, "w-theirs", scope="theirs-scope")])
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "theirs")
    _git(root, "checkout", "-q", "main")
    _write_ledger(root, lt, base + [_row(lt, "w-ours", scope="ours-scope")])
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "ours")
    r = _git(root, "merge", "--no-edit", "theirs", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    text = (root / lt.summary).read_text(encoding="utf-8")
    assert "<<<<<<<" not in text
    merged = sorted((json.loads(x) for x in (root / lt.path).read_text(encoding="utf-8").splitlines() if x.strip()),
                    key=lambda x: x["id"])
    assert {x["key"] for x in merged} == {"w-base", "w-ours", "w-theirs"}
    assert text == fl.render_summary(lt, merged)
    assert "ours-scope" in text and "theirs-scope" in text


def test_gate_inventory_render_is_regenerated_from_the_merged_inventory(tmp_path):
    root = _repo(tmp_path)
    inv_p, md_p = root / ga.INVENTORY_REL, root / ga.RENDERED_REL
    inv_p.parent.mkdir(parents=True)

    def write(gates, decisions):
        inv_p.write_text(json.dumps({"measured_over": "m", "gates": {g: {"severity": "x", "class": "c"} for g in gates},
                                     "decisions": decisions}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        md_p.write_text(ga.render_markdown(root) + "\n## Decision coverage matrix\n\n" + ga.render_matrix(root), encoding="utf-8")

    def dec(i, t):
        return {"id": i, "decision": t, "gate": "g"}

    write(["a"], [dec("D1", "one")])
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "base")
    _register(root)
    _git(root, "checkout", "-q", "-b", "theirs")
    write(["a", "gate-theirs"], [dec("D1", "one"), dec("D2", "theirs-decision")])
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "theirs")
    _git(root, "checkout", "-q", "main")
    write(["a", "gate-ours"], [dec("D1", "one"), dec("D2", "ours-decision")])
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "ours")
    r = _git(root, "merge", "--no-edit", "theirs", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    text = md_p.read_text(encoding="utf-8")
    assert "<<<<<<<" not in text
    for tok in ("gate-ours", "gate-theirs", "ours-decision", "theirs-decision"):
        assert tok in text
    assert text == ga.render_markdown(root) + "\n## Decision coverage matrix\n\n" + ga.render_matrix(root)


def test_unrenderable_render_surfaces_a_real_conflict(tmp_path):
    root = _repo(tmp_path)
    p = root / "project-history/gate-alignment/FINDINGS.md"
    p.parent.mkdir(parents=True)
    p.write_text("a\nb\nc\n")
    _git(root, "add", "-A"); _git(root, "commit", "-qm", "base")
    _register(root)
    _git(root, "checkout", "-q", "-b", "theirs"); p.write_text("a\nTHEIRS\nc\n"); _git(root, "commit", "-qam", "t")
    _git(root, "checkout", "-q", "main"); p.write_text("a\nOURS\nc\n"); _git(root, "commit", "-qam", "o")
    assert _git(root, "merge", "--no-edit", "theirs", check=False).returncode != 0
    text = p.read_text()
    assert "<<<<<<<" in text and "OURS" in text and "THEIRS" in text
