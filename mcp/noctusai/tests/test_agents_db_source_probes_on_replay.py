"""Agents 070 (DB-source dev agents): every GuardProbe runs on the REAL core + agents chain on PGlite and reports
`refused`.

Why: `agents.fonte_check` attacked with an UPDATE, but 070's BEFORE UPDATE trigger guard_agent_fonte_immutable
raises first, so the CHECK was never reached and the probe read `ambiguous`. That BLOCKED the agents W2 predeploy
(2026-11-10). Nothing ran these probes on the real chain, so it was wrong from 070 on. A probe whose attack is
pre-empted by another guard reads `ambiguous` here, never `refused`.
"""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_PROBES = vdg._AGENTS_DB_SOURCE_PROBES
_MIGS = {f"products/agents/backend/migrations/{m}" for p in _PROBES for m in p.migrations}


def test_every_db_source_probe_is_refused_on_the_real_chain(pglite):
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
