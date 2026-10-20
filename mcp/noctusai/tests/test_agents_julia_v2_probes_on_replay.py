"""Agents 031-040 (Julia v2): every GuardProbe that replaced a `_GUARD_PROBE_ALLOWLIST` "unapplied" entry
(A-polish #12) runs on the REAL core + agents chain on PGlite and reports `refused` -- the guard fires on the exact
forbidden write, and the probe's self-provisioned setup is valid SQL against the real schema (a broken setup would
read `ambiguous`, never `refused`)."""
from __future__ import annotations

import re
from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg
from tools.noctus.dev.compliance import _GUARD_PROBE_ALLOWLIST

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_PROBES = vdg._AGENTS_JULIA_V2_PROBES
_MIGS = {f"products/agents/backend/migrations/{m}" for p in _PROBES for m in p.migrations}


def test_the_probes_are_registered_and_no_031_to_040_allowlist_entry_is_left():
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    assert len({p.id for p in _PROBES}) == len(_PROBES)
    for p in _PROBES:
        assert by_id[p.id] is p and p.product == "agents" and p.migrations
    left = [(f, n) for f, n, _r in _GUARD_PROBE_ALLOWLIST
            if re.search(r"products/agents/backend/migrations/0(3[1-9]|40)_", f)]
    # the one guard a rolled-back probe cannot reach without fabricating a second platform org (rationale there)
    assert left == [("products/agents/backend/migrations/031_julia_v2_conteudo.sql", "agents_one_plataforma_per_key")]


def test_every_julia_v2_probe_is_refused_on_the_real_chain(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "agents", _MIGS, "worktree", {})
    # Fixture: the platform org production has (slug 'noctusai'), which two probes BORROW. Inserted with triggers
    # off -- in this core+agents-only chain other products' org triggers (ERP site config) have no tables.
    steps.append({"product": "agents", "file": "step:fixture-platform-org", "mode": "file", "twice": False, "sql": (
        "SET session_replication_role = replica;\n"
        "INSERT INTO public.organizations (nome, slug, is_platform) VALUES ('NoctusAI', 'noctusai-probe-fixture', true);\n"
        "SET session_replication_role = origin;")})
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
    fixture = next(st for st in res["steps"] if st["file"] == "step:fixture-platform-org")
    assert not fixture["failures"], fixture["failures"]
    bad = {k: v for k, v in out.items() if v != "refused"}
    assert not bad and len(out) == len(_PROBES), bad
