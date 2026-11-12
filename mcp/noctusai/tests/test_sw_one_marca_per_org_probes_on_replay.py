"""Social-wiring 339 (one brand per org, owner 2026-11-05): the `uq_marcas_one_per_org` GuardProbe and the older
`uq_marcas_one_primary_per_org` probe (210) both report `refused` on the REAL core + social-wiring chain on PGlite,
and 339 applies twice. Since 339 any second marca in an org is refused, so 210's probe accepts either index name."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_IDS = ("social_wiring.marcas.one_per_org", "social_wiring.marcas.one_primary_per_org")
_MIG = "products/social-wiring/backend/migrations/339_marca_one_per_org.sql"


def test_both_marca_probes_are_refused_on_the_real_chain(pglite):
    probes = [p for p in vdg.DEFAULT_REGISTRY if p.id in _IDS]
    assert sorted(p.id for p in probes) == sorted(_IDS)
    steps = mr._steps_for(Path(REPO_ROOT), "social-wiring", {_MIG}, "worktree", {})
    for p in probes:
        steps.append({"product": "social-wiring", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql), "mode": "file",
                      "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {st["file"]: st for st in res["steps"]}
    assert not by_file[Path(_MIG).name]["failures"], by_file[Path(_MIG).name]["failures"]
    out = {}
    for pid in _IDS:
        err = by_file[pid]["failures"][0]["error"] if by_file[pid]["failures"] else ""
        m = _SENT.search(err)
        out[pid] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    assert out == {pid: "refused" for pid in _IDS}, out
