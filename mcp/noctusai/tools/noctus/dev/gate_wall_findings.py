"""The `gate-walls` instance of the generic findings ledger (mechanism: findings_ledger;
KB § PATTERNS/common/living-findings-ledgers.md). Alignment loop, leg (c): a gate that fires in normal flow
(a wall), a demoted-noisy gate past its expiry, or a decision-matrix leg still `pending:` is a finding with an
owner, so misalignment surfaces without anyone running an audit (KB § PATTERNS/common/gate-methodology-sync.md).

The scanner is DETERMINISTIC (committed inventory only, never the machine-local event log), so `check` agrees on every
machine and in CI. Live effective-FP numbers stay in `noctus.dev.gate_alignment action=walls`. NEVER edit by hand.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from tools.noctus.dev import findings_ledger as gl
from tools.noctus.dev import gate_alignment as ga

NAME = "gate-walls"
KINDS = ("wall", "demoted-expired", "matrix-pending")


def current_rows(root: Path) -> dict[str, dict]:
    inv = ga.load_inventory(root)
    out: dict[str, dict] = {}
    today = _dt.date.today().isoformat()
    for gid, e in inv.get("gates", {}).items():
        fire = e.get("firings") or {}
        mech = e.get("mechanism", "")
        rem = str(e.get("remediation", ""))
        if (e.get("class") == "wall" and not mech.startswith("none") and not rem.startswith("FIXED")):
            out[f"wall:{gid}"] = {
                "section": "walls", "scope": e.get("owner") or "tooling-engineer", "target": gid, "kind": "wall",
                "severity": "high" if int(fire.get("count", 0)) >= 40 else "medium",
                "note": f"{fire.get('count', 0)} firings / {fire.get('sessions', 0)} sessions in normal flow. {rem or 'Construction leg missing.'}"}
        dem = e.get("demoted")
        if dem and str(dem.get("expiry", "9999")) < today:
            out[f"demoted:{gid}"] = {
                "section": "walls", "scope": e.get("owner") or "tooling-engineer", "target": gid, "kind": "demoted-expired",
                "severity": "high", "note": f"demoted-noisy past expiry {dem.get('expiry')}: research (cited sources), fix the detector, FP/TP tests, re-measure, re-promote."}
    for pm in ga.matrix_issues(root)[1]:
        out[f"matrix:{pm['decision']}:{pm['leg']}"] = {
            "section": "walls", "scope": pm["pending"].split(":", 1)[-1], "target": f"{pm['decision']}/{pm['leg']}",
            "kind": "matrix-pending", "severity": "medium", "note": f"decision {pm['decision']} leg `{pm['leg']}` is {pm['pending']}."}
    return out


LEDGER = gl.register_ledger(gl.LedgerType(
    name=NAME, prefix="GW", path="project-history/gate-alignment/findings.ndjson",
    summary="project-history/gate-alignment/FINDINGS.md",
    extra={"kind": KINDS}, sections=("walls",), scanner=current_rows,
))
