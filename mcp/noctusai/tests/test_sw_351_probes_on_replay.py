"""SW 351 (Biblioteca platform scope, M2) GuardProbes executed against the REAL social-wiring chain on PGlite.

Same idea as the 350 replay test: the probes in `verify_db_guards.DEFAULT_REGISTRY` normally only run against prod; this
runs their exact SQL (through `wrap_rollback_only`) on the replayed chain after migration 351, so a probe that cannot work
(a wrong column in a fixture, an unmodelled trigger) fails HERE, not as a surprise gate-red in prod. Each refusal probe
must come back `refused`, each sanctioned-write probe `allowed`, the browser-grant assertion `clean`.
"""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_EXPECTED = {"write_refusal": "refused", "write_allowed": "allowed", "state_assertion": "clean"}


def _probes():
    return [p for p in vdg.DEFAULT_REGISTRY if p.id.startswith("sw351_")]


def test_every_351_probe_is_registered_and_names_the_migration():
    probes = _probes()
    assert len(probes) >= 15
    assert {p.migrations for p in probes} == {("351_cs_library_platform_scope.sql",)}
    assert len({p.id for p in probes}) == len(probes)
    assert {"cs_perfil_eventos_imutavel", "cs_perfis_monitorados_plataforma_handle_uq", "cs_virais_ig_shortcode_uq",
            "cs_virais_codigo_uq", "cs_virais_origem_inclusao_valida", "cs_perfil_purgar",
            "cs_library_platform_tier"} <= {p.guard_name for p in probes}


def test_probes_pass_on_the_real_chain_with_351(pglite):
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "social-wiring", set(), "worktree", {})
    probes = _probes()
    for p in probes:
        steps.append({"product": "social-wiring", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql),
                      "mode": "file", "twice": False})
    res = mr._run_harness(steps, 1800, None)
    assert res.get("ok"), res
    by_file = {st["file"]: st for st in res["steps"]}
    outcomes: dict[str, str] = {}
    for p in probes:
        st = by_file[p.id]
        err = st["failures"][0]["error"] if st["failures"] else ""
        m = _SENT.search(err)
        outcomes[p.id] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    assert outcomes == {p.id: _EXPECTED[p.kind] for p in probes}, outcomes
