"""SW 358 (roteiro-first in the unified chat, M6) GuardProbes executed against the REAL social-wiring chain on PGlite.

The probes in `verify_db_guards.DEFAULT_REGISTRY` normally only ever run against prod; this runs their exact SQL
(through `wrap_rollback_only`) on the replayed chain after migration 358, so a probe that cannot work (a wrong column
in a fixture, an unmodelled trigger, a NOT NULL column the fixture forgot) fails HERE, not as a surprise gate-red in
prod. Each refusal probe must come back `refused`, each sanctioned-write probe (the usos FK-action carve-outs) `allowed`
-- a `permitted` / `blocked` / `ambiguous` / `no_fixture` here is a probe or migration bug.
"""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_EXPECTED = {"write_refusal": "refused", "write_allowed": "allowed"}


def _probes():
    return [p for p in vdg.DEFAULT_REGISTRY if p.id.startswith("sw358_")]


def test_every_358_probe_is_registered_and_names_the_migration():
    probes = _probes()
    assert len(probes) == 11
    assert {p.migrations for p in probes} == {("358_cs_roteiro_primeiro.sql",)}
    assert len({p.id for p in probes}) == len(probes)
    assert {"cs_chat_propostas_tipo_check", "cs_chat_propostas_tipo_campos_check", "cs_chat_propostas_titulo_check",
            "cs_chat_propostas_formato_check", "cs_chat_propostas_texto_check", "cs_fluxo_eventos_tipo_check",
            "cs_headlines_modo_check", "cs_roteiros_conversa_proposta_uq"} == {p.guard_name for p in probes}


def test_probes_pass_on_the_real_chain_with_358(pglite):
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
