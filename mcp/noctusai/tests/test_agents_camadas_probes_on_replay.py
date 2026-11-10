"""Agents 073 (agent layers BASE -> SDR -> agent): every GuardProbe of the migration runs on the REAL core + agents
chain on PGlite and reports `refused`. Own group, like 049's geracao probes: the 012-017 studio-probe class excludes it."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_PROBES = vdg._AGENTS_CAMADAS_PROBES
_MIGS = {f"products/agents/backend/migrations/{m}" for p in _PROBES for m in p.migrations}


def test_the_probes_are_registered():
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    assert {p.guard_name for p in _PROBES} == {"agents_camada_check", "guard_agent_camada", "guard_version_pai_pin"}
    for p in _PROBES:
        assert by_id[p.id] is p and p.product == "agents" and p.migrations[-1] == "073_agent_camadas.sql"


def test_every_camadas_probe_is_refused_on_the_real_chain(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "agents", _MIGS, "worktree", {})
    for p in _PROBES:
        steps.append({"product": "agents", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql), "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    ids = {p.id for p in _PROBES}
    out: dict[str, str] = {}
    for st in res["steps"]:
        if st["file"] in ids:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    bad = {k: v for k, v in out.items() if v != "refused"}
    assert not bad and len(out) == len(_PROBES), bad
