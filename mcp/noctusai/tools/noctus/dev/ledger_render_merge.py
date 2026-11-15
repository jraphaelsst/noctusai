"""Merge a GENERATED render (findings-ledger FINDINGS.md, gate-alignment-inventory.md) by regenerating it from its source.

Two parallel branches that each reconcile a ledger / declare a gate both rewrite the SAME generated file, so a text
merge conflicts on pure machine churn (22 transcript hotspots). The render is a pure function of its source
(`findings.ndjson`, `gate-alignment-inventory.json`), so the right merge is: merge the SOURCE the way git merges it
(ndjson = `merge=union`, inventory = the `gate-inventory` driver), then render that.

A merge driver only receives the render's own %O/%A/%B, and `ort` has not yet touched the work tree, so the sources
are recovered from git by CONTENT: the commit that introduced the render blob also carried its source. Anything that
cannot be recovered returns None and the shell half falls back to the plain 3-way merge (markers + both sides).
KB § PATTERNS/common/auto-generated-merge-drivers.md
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from tools.noctus.dev import findings_ledger as fl
from tools.noctus.dev import gate_alignment as ga

REPO_ROOT = Path(__file__).resolve().parents[5]


def _git(root: Path, *args: str, stdin: str | None = None) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, input=stdin, timeout=60, check=False)
    return p.returncode, p.stdout


def source_for_render(root: Path, render_rel: str, render_file: Path, source_rel: str) -> str | None:
    """The source file as it was in the commit that carried this exact render blob (None: not recoverable)."""
    if not render_file.is_file() or render_file.stat().st_size == 0:
        return None
    rc, blob = _git(root, "hash-object", str(render_file))
    if rc != 0 or not blob.strip():
        return None
    rc, commits = _git(root, "log", "--all", "--format=%H", f"--find-object={blob.strip()}", "--", render_rel)
    for c in commits.split():
        # --find-object also lists commits that REMOVED the blob; only one that HAS it carries its source
        rc, has = _git(root, "rev-parse", f"{c}:{render_rel}")
        if rc != 0 or has.strip() != blob.strip():
            continue
        rc, text = _git(root, "show", f"{c}:{source_rel}")
        if rc == 0:
            return text
    return None


def _union(base: str, ours: str, theirs: str) -> str:
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for name, text in (("o", ours), ("b", base), ("t", theirs)):
            p = Path(d) / name
            p.write_text(text, encoding="utf-8")
            paths.append(str(p))
        _rc, merged = _git(Path(d), "merge-file", "-p", "--union", *paths)
        return merged


def merge_render(rel: str, base_f: Path, ours_f: Path, theirs_f: Path, root: Path | None = None) -> tuple[str | None, list[str]]:
    """(merged render text | None when not derivable here, notes)."""
    root = root or REPO_ROOT
    notes: list[str] = []
    ledger = next((lt for lt in fl.ledgers().values() if lt.summary == rel), None)
    inv_md = str(ga.RENDERED_REL)
    if ledger is None and rel != inv_md:
        return None, [f"{rel}: not a registered generated render"]
    src_rel = ledger.path if ledger else str(ga.INVENTORY_REL)
    ours = source_for_render(root, rel, ours_f, src_rel)
    if ours is None and (root / src_rel).is_file():
        ours = (root / src_rel).read_text(encoding="utf-8")  # a merge/rebase runs on a tree at HEAD
    theirs = source_for_render(root, rel, theirs_f, src_rel)
    base = source_for_render(root, rel, base_f, src_rel)
    if ours is None or theirs is None:
        return None, [f"{rel}: source {src_rel} not recoverable from the render blobs"]
    if ledger is not None:
        merged = _union(base or "", ours, theirs)
        rows: dict[str, dict] = {}
        for line in merged.splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["key"]] = r
        return fl.render_summary(ledger, sorted(rows.values(), key=lambda r: r["id"])), notes
    if base is None:
        return None, [f"{rel}: base inventory not recoverable"]
    text, conflicted, notes = ga.merge_inventory(base, ours, theirs)
    if conflicted:
        return None, notes
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / ga.INVENTORY_REL).parent.mkdir(parents=True)
        (tmp / ga.INVENTORY_REL).write_text(text, encoding="utf-8")
        if (root / ga.BASELINE_REL).is_file():
            (tmp / ga.BASELINE_REL).write_text((root / ga.BASELINE_REL).read_text(encoding="utf-8"), encoding="utf-8")
        return ga.render_markdown(tmp) + "\n## Decision coverage matrix\n\n" + ga.render_matrix(tmp), notes
