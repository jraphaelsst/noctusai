"""Core `products.destaque_no_site` (migration 100) GuardProbes executed against the REAL core chain
on PGlite: the range CHECK, the hidden-but-featured CHECK and the partial UNIQUE must each refuse a
bad write and name their own constraint."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")


def _outcomes() -> dict[str, str]:
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "core", set(), "worktree", {})
    probes = list(vdg._PRODUCTS_DESTAQUE_PROBES)
    assert len(probes) == 3
    for p in probes:
        steps.append({"product": "core", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql),
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


def test_probes_are_registered():
    assert all(p in vdg.DEFAULT_REGISTRY for p in vdg._PRODUCTS_DESTAQUE_PROBES)


def test_every_destaque_guard_refuses_on_the_real_chain(pglite):
    out = _outcomes()
    assert set(out.values()) == {"refused"}, out
    assert len(out) == 3
