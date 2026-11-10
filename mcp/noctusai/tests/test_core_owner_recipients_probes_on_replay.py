"""Core 118 (owner-notice recipients + events) guard probes EXECUTED on the REAL core chain on PGlite.

Every registered 118 probe (events: update / delete / truncate / direct_insert; recipients: numero_update /
truncate / plain_delete / unstamped_update) runs against the replayed chain and must report ``refused`` -- the
control's evidence is the refusal observed, not the registration. ``direct_insert_refused`` uses
``SET LOCAL ROLE service_role`` (the PGlite stubs create the Supabase roles, as the lockdown on-replay tests rely on).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr
from tools.noctus.dev import verify_db_guards as vdg

_SENT = re.compile(r"NOC_PROBE:(\w+):")
_MIG = "118_notification_owner_recipients.sql"
_PROBES = [p for p in vdg.DEFAULT_REGISTRY if _MIG in p.migrations]
_EXPECTED_IDS = {
    "notification_owner_recipient_events.update_refused",
    "notification_owner_recipient_events.delete_refused",
    "notification_owner_recipient_events.truncate_refused",
    "notification_owner_recipient_events.direct_insert_refused",
    "notification_owner_recipients.numero_update_refused",
    "notification_owner_recipients.truncate_refused",
    "notification_owner_recipients.plain_delete_refused",
    "notification_owner_recipients.unstamped_update_refused",
}


def _verdicts() -> dict[str, str]:
    steps = mr._steps_for(Path(REPO_ROOT), "core", set(), "worktree", {})
    for p in _PROBES:
        steps.append({"product": "core", "file": p.id, "sql": vdg.wrap_rollback_only(p.sql),
                      "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    ids = {p.id for p in _PROBES}
    out: dict[str, str] = {}
    for st in res["steps"]:
        if st["file"] in ids:
            err = st["failures"][0]["error"] if st["failures"] else ""
            m = _SENT.search(err)
            out[st["file"]] = m.group(1) if m else f"UNCLASSIFIED: {err}"
    return out


def test_every_118_probe_is_registered():
    assert {p.id for p in _PROBES} == _EXPECTED_IDS


def test_every_118_probe_refuses_on_the_real_chain(pglite):
    """One replay of the whole chain, then every probe's verdict (one chain run, not one per probe)."""
    verdicts = _verdicts()
    assert set(verdicts) == _EXPECTED_IDS, verdicts
    assert {k: v for k, v in verdicts.items() if v != "refused"} == {}, verdicts


_POSITIVE_SQL = """
DO $t$
DECLARE
  v_id uuid := gen_random_uuid();
  v_a1 uuid := gen_random_uuid();
  v_a2 uuid := gen_random_uuid();
  v_a3 uuid := gen_random_uuid();
  v_ret uuid;
  v_n int;
BEGIN
  SET LOCAL ROLE service_role;
  INSERT INTO public.notification_owner_recipients (id, numero, alterado_por, alterado_em)
  VALUES (v_id, '+5500000000077', v_a1, now());
  PERFORM pg_sleep(0.01);
  UPDATE public.notification_owner_recipients
     SET ativo = false, alterado_por = v_a2, alterado_em = clock_timestamp() WHERE id = v_id;
  PERFORM pg_sleep(0.01);
  UPDATE public.notification_owner_recipients
     SET nome = 'Dono', alterado_por = v_a3, alterado_em = clock_timestamp() WHERE id = v_id;
  SELECT count(*) INTO v_n FROM public.notification_owner_recipient_events
   WHERE recipient_id = v_id AND evento = 'adicionado' AND ator = v_a1;
  IF v_n <> 1 THEN RAISE EXCEPTION 'POS: expected 1 adicionado by a1, got %', v_n; END IF;
  SELECT count(*) INTO v_n FROM public.notification_owner_recipient_events
   WHERE recipient_id = v_id AND evento = 'desativado' AND ator = v_a2;
  IF v_n <> 1 THEN RAISE EXCEPTION 'POS: expected 1 desativado by a2, got %', v_n; END IF;
  SELECT count(*) INTO v_n FROM public.notification_owner_recipient_events
   WHERE recipient_id = v_id AND evento = 'renomeado' AND ator = v_a3;
  IF v_n <> 1 THEN RAISE EXCEPTION 'POS: expected 1 renomeado by a3, got %', v_n; END IF;

  v_ret := public.remover_destinatario_dono(v_id, v_a2);
  IF v_ret IS DISTINCT FROM v_id THEN RAISE EXCEPTION 'POS: rpc did not return the id (%)', v_ret; END IF;
  IF EXISTS (SELECT 1 FROM public.notification_owner_recipients WHERE id = v_id) THEN
    RAISE EXCEPTION 'POS: row still present after removal';
  END IF;
  SELECT count(*) INTO v_n FROM public.notification_owner_recipient_events
   WHERE recipient_id = v_id AND evento = 'removido' AND ator = v_a2;
  IF v_n <> 1 THEN RAISE EXCEPTION 'POS: expected exactly 1 removido by a2, got %', v_n; END IF;
  SELECT count(*) INTO v_n FROM public.notification_owner_recipient_events
   WHERE recipient_id = v_id AND evento = 'removido';
  IF v_n <> 1 THEN RAISE EXCEPTION 'POS: removido events %', v_n; END IF;
  v_ret := public.remover_destinatario_dono(v_id, v_a2);
  IF v_ret IS NOT NULL THEN RAISE EXCEPTION 'POS: second removal returned %', v_ret; END IF;
  SELECT count(*) INTO v_n FROM public.notification_owner_recipient_events WHERE recipient_id = v_id;
  IF v_n <> 4 THEN RAISE EXCEPTION 'POS: expected 4 events in total, got %', v_n; END IF;
  RAISE EXCEPTION 'POS_OK';
END $t$;
"""


def test_positive_paths_work_on_the_real_chain(pglite):
    """A guard that refuses every delete must not hide a removal that never works."""
    steps = mr._steps_for(Path(REPO_ROOT), "core", set(), "worktree", {})
    steps.append({"product": "core", "file": "positive-118", "sql": _POSITIVE_SQL, "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    st = next(s for s in res["steps"] if s["file"] == "positive-118")
    err = st["failures"][0]["error"] if st["failures"] else ""
    assert "POS_OK" in err, err
