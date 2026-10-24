"""Migration 306's GuardProbes executed against the REAL social-wiring chain on
PGlite: every guard of that migration must read `refused` once applied (prod
reads `no_fixture`/an error until then). The probe count is DERIVED from the
registry -- adding a guard adds a probe here, never a hardcoded number."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_SEED = (
    "WITH o AS (INSERT INTO public.organizations (nome, slug) VALUES ('NOC seed', 'noc-seed-306') RETURNING id) "
    "INSERT INTO social_wiring.imovel_registry (org_id, codigo_canonical) SELECT id, 'NOC_SEED' FROM o;"
)


def _probes():
    return [p for p in vdg.DEFAULT_REGISTRY if p in vdg._SW_CAMPOS_MANUAIS_PROBES]


def _outcomes() -> dict[str, str]:
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "social-wiring", set(), "worktree", {})
    probes = _probes()
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


def test_the_registry_carries_every_306_probe():
    assert _probes() and len(_probes()) == len(vdg._SW_CAMPOS_MANUAIS_PROBES)


def test_every_306_guard_refuses_on_the_real_chain(pglite):
    out = _outcomes()
    assert set(out.values()) == {"refused"}, out
    assert len(out) == len(vdg._SW_CAMPOS_MANUAIS_PROBES)
