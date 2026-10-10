"""SW 240 GuardProbes executed against the REAL social-wiring chain on PGlite.

The probes in `verify_db_guards.DEFAULT_REGISTRY` normally only ever run
against prod; this runs their exact SQL (through `wrap_rollback_only`) on the
replayed chain after migration 240, so a probe that cannot work (wrong column,
an unmodelled trigger) fails HERE, not as a surprise gate-red in prod. A second
run replaces 240's function with the pre-240 behaviour to prove the probe
discriminates (the old silent drop is a `violation`).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_M240 = "products/social-wiring/backend/migrations/240_spawn_funil_card_sem_descarte_silencioso.sql"
_IDS = ("social-wiring.atendimentos.org_meta_lead.unique", "social-wiring.spawn_funil_card.no_silent_drop")
_SENT = re.compile(r"NOC_PROBE:(\w+):")


def _outcomes(overrides: dict[str, str]) -> dict[str, str]:
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "social-wiring", set(), "worktree", overrides)
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY if p.id in _IDS}
    assert set(by_id) == set(_IDS)
    for pid, p in by_id.items():
        steps.append({"product": "social-wiring", "file": pid, "sql": vdg.wrap_rollback_only(p.sql),
                      "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    out = {}
    for st in res["steps"]:
        if st["file"] in _IDS:
            err = (st["failures"][0]["error"] if st["failures"] else "")
            m = _SENT.search(err)
            out[st["file"]] = (m.group(1) if m else f"UNCLASSIFIED: {err}")
    return out


def test_probes_pass_on_the_real_chain_with_240(pglite):
    assert _outcomes({}) == {
        "social-wiring.atendimentos.org_meta_lead.unique": "refused",
        "social-wiring.spawn_funil_card.no_silent_drop": "allowed",
    }


def test_spawn_probe_flags_the_pre_240_silent_drop(pglite):
    root = Path(REPO_ROOT)
    sql = (root / _M240).read_text(encoding="utf-8")
    old_fn = (root / "products/social-wiring/backend/migrations/090_um_card_por_lead.sql").read_text(encoding="utf-8")
    old_fn = old_fn[old_fn.index("CREATE OR REPLACE FUNCTION"):old_fn.index("$function$;") + len("$function$;")]
    start = sql.index("-- ─── 3.")
    out = _outcomes({_M240: sql[:start] + old_fn + "\n"})
    assert out["social-wiring.spawn_funil_card.no_silent_drop"] == "violation", out
