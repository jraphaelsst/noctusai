"""The Julia wave-4 (migration 271, reengajamento) GuardProbes executed against the REAL social-wiring chain
on PGlite: every guard of that migration must read `refused` once applied (prod reads `no_fixture` until then)."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_SEED = (
    "INSERT INTO social_wiring.imovel_registry (org_id, codigo_canonical) "
    "VALUES (gen_random_uuid(), 'NOC_SEED');"
)


def _outcomes() -> dict[str, str]:
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "social-wiring", set(), "worktree", {})
    probes = [p for p in vdg.DEFAULT_REGISTRY if p in vdg._SW_JULIA_REENG_PROBES]
    assert len(probes) == 10
    steps.append({"product": "social-wiring", "file": "seed", "sql": _SEED, "mode": "file", "twice": False})
    for p in probes:
        steps.append({"product": "social-wiring", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql),
                      "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    ids = {p.id for p in probes}
    out = {}
    for st in res["steps"]:
        if st["file"] in ids:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    return out


def test_every_julia_reeng_guard_refuses_on_the_real_chain(pglite):
    out = _outcomes()
    assert set(out.values()) == {"refused"}, out
    assert len(out) == 10
