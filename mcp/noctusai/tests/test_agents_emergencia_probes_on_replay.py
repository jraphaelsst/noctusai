"""Agents 079: the two new GuardProbes are registered and REFUSE on the real core + agents chain (PGlite)."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_PROBES = tuple(vdg._AGENTS_EMERGENCIA_PROBES)
_MIGS = {"products/agents/backend/migrations/079_emergencia_inatividade.sql"}


def test_the_079_probes_are_registered():
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    assert len(_PROBES) == 2
    for p in _PROBES:
        assert by_id[p.id] is p and p.product == "agents"


def test_079_probes_are_refused_on_the_real_chain(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "agents", _MIGS, "worktree", {})
    for p in _PROBES:
        steps.append({"product": "agents", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql), "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    out = {}
    for st in res["steps"]:
        if st["file"] in {p.id for p in _PROBES}:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    bad = {k: v for k, v in out.items() if v != "refused"}
    assert not bad and len(out) == len(_PROBES), bad
