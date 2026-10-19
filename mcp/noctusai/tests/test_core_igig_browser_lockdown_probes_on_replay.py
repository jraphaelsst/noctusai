"""Core 086 (secrets tables) + igig 044 (schema) browser lockdown, security findings #1/#2/#3/#5, on the REAL chain on PGlite.

1. With the migration applied (twice -- idempotency) every lockdown probe is ``clean``.
2. With it replaced by a no-op the same probes report ``violation`` -- non-vacuous (the 055 / 006.. policies and
   001's ``GRANT ALL`` really expose the tables without it).
3. Behaviour, not just catalog: as ``authenticated`` a SELECT on a locked table is refused; igig ``status_pagina`` reads.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")

_CASES = {
    "core": ("products/core/backend/migrations/086_revoke_browser_secrets_tables.sql", vdg._CORE_BROWSER_LOCKDOWN_PROBES,
             "SELECT 1 FROM public.org_settings LIMIT 1", None),
    "igig": ("products/igig/backend/migrations/044_revoke_authenticated_content.sql", vdg._IGIG_BROWSER_LOCKDOWN_PROBES,
             "SELECT 1 FROM igig.cliente LIMIT 1", "SELECT 1 FROM igig.status_pagina LIMIT 1"),
}


def _behaviour_sql(denied: str, allowed: str | None) -> str:
    ok = f"  PERFORM 1 FROM ({allowed}) q;\n" if allowed else ""
    return f"""
DO $t$ BEGIN
  SET LOCAL ROLE authenticated;
  BEGIN
    PERFORM 1 FROM ({denied}) q;
    RESET ROLE;
    RAISE EXCEPTION 'ASSERT authenticated could read a locked table';
  EXCEPTION WHEN insufficient_privilege THEN
    NULL;
  END;
{ok}  RESET ROLE;
END $t$;
"""


def _run(product: str, overrides: dict[str, str], with_behaviour: bool = False) -> tuple[dict[str, str], list[dict]]:
    mig, probes, denied, allowed = _CASES[product]
    steps = mr._steps_for(Path(REPO_ROOT), product, {mig}, "worktree", overrides)
    if product == "core":
        # Supabase's default ACL on `public` hands every new table to anon/authenticated; the PGlite stubs do not
        # model it, so replay it right before 086 -- otherwise the grant probe is vacuously clean without the fix.
        at = next(i for i, st in enumerate(steps) if st["file"] == Path(mig).name)
        steps.insert(at, {"product": "core", "file": "step:supabase-default-acl", "mode": "file", "twice": False, "sql": (
            "GRANT ALL ON public.org_settings, public.webhook_endpoints, public.webhook_deliveries, public.api_keys "
            "TO anon, authenticated;")})
    for p in probes:
        steps.append({"product": product, "file": p.id, "sql": vdg.wrap_rollback_only(p.sql), "mode": "file", "twice": False})
    if with_behaviour:
        steps.append({"product": product, "file": "step:behaviour", "sql": _behaviour_sql(denied, allowed), "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    ids = {p.id for p in probes}
    out: dict[str, str] = {}
    other: list[dict] = []
    for st in res["steps"]:
        if st["file"] in ids:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
        elif st["failures"] and st["product"] == product and st["file"] in (Path(mig).name, "step:behaviour"):
            # (core's own history files carry known residue, judged by migration-replay.json -- not this test's concern)
            other.append(st)
    return out, other


@pytest.mark.parametrize("product", sorted(_CASES))
def test_probes_registered_and_declare_the_migration(product):
    mig, probes, _d, _a = _CASES[product]
    by_id = {p.id: p for p in vdg.DEFAULT_REGISTRY}
    assert len(probes) == 2
    for p in probes:
        assert by_id[p.id] is p
        assert Path(mig).name in p.migrations


@pytest.mark.parametrize("product", sorted(_CASES))
def test_every_probe_is_clean_with_the_migration(pglite, product):
    out, other = _run(product, {}, with_behaviour=True)
    assert other == [], other
    assert out == {p.id: "clean" for p in _CASES[product][1]}


@pytest.mark.parametrize("product", sorted(_CASES))
def test_without_the_migration_the_probes_report_violation(pglite, product):
    mig, probes, _d, _a = _CASES[product]
    out, other = _run(product, {mig: "SELECT 1;\n"})
    assert other == [], other
    assert out == {p.id: "violation" for p in probes}, out
