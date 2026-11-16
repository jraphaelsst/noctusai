"""Social-wiring 344 + 345 (ImobShotAI) on REAL Postgres (PGlite, the migration-replay harness).

344 created the cards and a hand-written `imobshot_eventos`; 345 renders the seed transition_log primitive for the card
(`imobshot_card_events`), copies every legacy event into it, re-points the three service-only functions at it and makes
the hand-written table read-only (the DROP is a later contract migration). Here: 345 applies twice; legacy rows (inserted with explicit timestamps, prod-shaped, BEFORE 345)
come out as the same events with the same ids, timestamps, actors and details; an unmappable row aborts the migration with
the old table intact; and the three functions behave as the repository relies on. Each scenario is a DO block that RAISES
on any deviation, so a step with no failures is a pass.

Scope note: PostgREST's `fotos_lotes!inner(criado_por)` embed (the corretor board filter) cannot run on PGlite; the test
runs the equivalent SQL (an inner join/EXISTS on `fotos_lotes.card_id`) and asserts a card appears once even when the
corretor created several of its lotes. Concurrency is modelled by the second call hitting the unique key."""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_MIG = "products/social-wiring/backend/migrations/345_imobshot_card_transition_log.sql"
_MIG_NAME = Path(_MIG).name

# Prod-shaped legacy history, inserted straight into the table 344 created (explicit, distinct `at`s as every real
# RPC call had its own transaction). Card A: created -> link -> two stage moves (one by the worker, no actor).
_LEGACY_OK = """
DO $$ DECLARE
  o uuid := '00000000-0000-0000-0000-0000000000a1'; ca uuid := '00000000-0000-0000-0000-00000000ca01';
  cb uuid := '00000000-0000-0000-0000-00000000ca02'; u uuid := '00000000-0000-0000-0000-0000000000b1';
BEGIN
  INSERT INTO social_wiring.imobshot_cards (id, org_id, imovel_codigo, etapa) VALUES
    (ca, o, 'LEG1', 'fotos_aprovadas'), (cb, o, 'LEG2', 'fotos_enviadas');
  INSERT INTO social_wiring.imobshot_eventos (id, org_id, card_id, tipo, etapa_de, etapa_para, actor_id, at, detalhe) VALUES
    ('00000000-0000-0000-0000-0000000e0001', o, ca, 'card_criado',    NULL,              'fotos_enviadas',  u,    '2026-11-01 10:00:00+00', '{}'),
    ('00000000-0000-0000-0000-0000000e0002', o, ca, 'lote_vinculado', NULL,              NULL,              u,    '2026-11-01 10:00:00+00', '{"lote_id": "L1"}'),
    ('00000000-0000-0000-0000-0000000e0003', o, ca, 'etapa_mudou',    'fotos_enviadas',  'fotos_em_edicao', NULL, '2026-11-01 10:05:00+00', '{}'),
    ('00000000-0000-0000-0000-0000000e0004', o, ca, 'etapa_mudou',    'fotos_em_edicao', 'fotos_aprovadas', u,    '2026-11-01 11:00:00+00', '{}'),
    ('00000000-0000-0000-0000-0000000e0005', o, cb, 'card_criado',    NULL,              'fotos_enviadas',  NULL, '2026-11-02 09:00:00+00', '{}');
  CREATE TABLE social_wiring._fx_legacy AS SELECT * FROM social_wiring.imobshot_eventos;
END $$;"""

# A history that cannot be mapped: the stage chain has a gap (the move claims it left a stage the card was never in).
_LEGACY_BAD = """
DO $$ DECLARE o uuid := gen_random_uuid(); c uuid := gen_random_uuid(); BEGIN
  INSERT INTO social_wiring.imobshot_cards (id, org_id, imovel_codigo, etapa) VALUES (c, o, 'BAD1', 'fotos_aprovadas');
  INSERT INTO social_wiring.imobshot_eventos (org_id, card_id, tipo, etapa_de, etapa_para, at) VALUES
    (o, c, 'card_criado', NULL, 'fotos_enviadas', '2026-11-01 10:00:00+00'),
    (o, c, 'etapa_mudou', 'fotos_em_revisao', 'fotos_aprovadas', '2026-11-01 11:00:00+00');
END $$;"""

_MIGRATED = {
    "legacy_rows_moved_losslessly": """
DO $$ DECLARE n int; k int; BEGIN
  IF to_regclass('social_wiring.imobshot_eventos') IS NULL THEN RAISE EXCEPTION 'legacy table dropped (contract step is a later migration)'; END IF;
  SELECT count(*) INTO n FROM social_wiring._fx_legacy;
  SELECT count(*) INTO k FROM social_wiring.imobshot_card_events e JOIN social_wiring._fx_legacy l ON l.id = e.id;
  IF n <> 5 OR k <> 5 THEN RAISE EXCEPTION 'legacy=% moved=%', n, k; END IF;
  -- same id / org / card / actor / timestamps / detail, intent kept in data.legacy_tipo
  SELECT count(*) INTO k FROM social_wiring.imobshot_card_events e JOIN social_wiring._fx_legacy l ON l.id = e.id
   WHERE e.org_id = l.org_id AND e.entity_id = l.card_id AND e.actor_id IS NOT DISTINCT FROM l.actor_id
     AND e.occurred_at = l.at AND e.recorded_at = l.at AND e.data->>'legacy_tipo' = l.tipo
     AND (e.data - 'legacy_tipo' - 'migrated_from') = l.detalhe
     AND e.actor_kind = CASE WHEN l.actor_id IS NULL THEN 'system' ELSE 'user' END;
  IF k <> 5 THEN RAISE EXCEPTION 'fields differ on % of 5 rows', 5 - k; END IF;
  -- card A: seq order + the stage chain (a link moves no stage: from = to)
  IF (SELECT string_agg(seq || ':' || event_type || ':' || COALESCE(from_state, '-') || '>' || to_state, ' | ' ORDER BY seq)
        FROM social_wiring.imobshot_card_events WHERE entity_id = '00000000-0000-0000-0000-00000000ca01')
     <> '1:created:->fotos_enviadas | 2:lote_vinculado:fotos_enviadas>fotos_enviadas | 3:etapa_mudou:fotos_enviadas>fotos_em_edicao | 4:etapa_mudou:fotos_em_edicao>fotos_aprovadas'
  THEN RAISE EXCEPTION 'card A chain differs'; END IF;
  IF (SELECT count(*) FROM social_wiring.imobshot_card_events WHERE entity_id = '00000000-0000-0000-0000-00000000ca02') <> 1 THEN
    RAISE EXCEPTION 'card B has no single created event'; END IF;
END $$;""",
    "obter_ou_criar_idempotent": """
DO $$ DECLARE o uuid := gen_random_uuid(); u uuid := gen_random_uuid(); a jsonb; b jsonb; n int; BEGIN
  a := social_wiring.imobshot_obter_ou_criar_card(o, 'ONE1', u);
  b := social_wiring.imobshot_obter_ou_criar_card(o, 'ONE1', u);
  IF NOT (a->>'criado')::boolean OR (b->>'criado')::boolean OR a->>'id' <> b->>'id' THEN
    RAISE EXCEPTION 'not idempotent: % %', a, b; END IF;
  SELECT count(*) INTO n FROM social_wiring.imobshot_cards WHERE org_id = o;
  IF n <> 1 THEN RAISE EXCEPTION 'cards=%', n; END IF;
  SELECT count(*) INTO n FROM social_wiring.imobshot_card_events
   WHERE org_id = o AND event_type = 'created' AND seq = 1 AND from_state IS NULL AND to_state = 'fotos_enviadas' AND actor_kind = 'user';
  IF n <> 1 THEN RAISE EXCEPTION 'created=%', n; END IF;
END $$;""",
    "vincular_lote_atomic": """
DO $$ DECLARE o uuid := gen_random_uuid(); u uuid := gen_random_uuid(); c uuid; l uuid; other uuid; n int; ok boolean; BEGIN
  c := (social_wiring.imobshot_obter_ou_criar_card(o, 'ONE2', u)->>'id')::uuid;
  INSERT INTO social_wiring.fotos_lotes (org_id, nome, criado_por, origem, velocidade)
    VALUES (o, 'x', u, 'vista', 'urgente') RETURNING id INTO l;
  ok := social_wiring.imobshot_vincular_lote(c, l, u);
  IF NOT ok THEN RAISE EXCEPTION 'link refused'; END IF;
  IF (SELECT card_id FROM social_wiring.fotos_lotes WHERE id = l) <> c THEN RAISE EXCEPTION 'card_id not set'; END IF;
  SELECT count(*) INTO n FROM social_wiring.imobshot_card_events
   WHERE entity_id = c AND event_type = 'lote_vinculado' AND data->>'lote_id' = l::text
     AND from_state = 'fotos_enviadas' AND to_state = 'fotos_enviadas' AND seq = 2;
  IF n <> 1 THEN RAISE EXCEPTION 'lote_vinculado=%', n; END IF;
  -- linking again is a no-op (no second event); another org's lote is refused
  IF social_wiring.imobshot_vincular_lote(c, l, u) THEN RAISE EXCEPTION 'relink wrote'; END IF;
  INSERT INTO social_wiring.fotos_lotes (org_id, nome, criado_por, origem, velocidade)
    VALUES (gen_random_uuid(), 'y', u, 'vista', 'urgente') RETURNING id INTO other;
  IF social_wiring.imobshot_vincular_lote(c, other, u) THEN RAISE EXCEPTION 'cross-org link accepted'; END IF;
  SELECT count(*) INTO n FROM social_wiring.imobshot_card_events WHERE entity_id = c;
  IF n <> 2 THEN RAISE EXCEPTION 'events after refused links=%', n; END IF;
  -- the corretor board filter, as SQL: a card appears ONCE however many lotes the corretor created
  INSERT INTO social_wiring.fotos_lotes (org_id, nome, criado_por, origem, velocidade, card_id)
    VALUES (o, 'z', u, 'vista', 'urgente', c);
  SELECT count(*) INTO n FROM social_wiring.imobshot_cards k
   WHERE k.org_id = o AND EXISTS (SELECT 1 FROM social_wiring.fotos_lotes x WHERE x.card_id = k.id AND x.criado_por = u);
  IF n <> 1 THEN RAISE EXCEPTION 'board filter rows=%', n; END IF;
END $$;""",
    "aplicar_etapa_only_on_change": """
DO $$ DECLARE o uuid := gen_random_uuid(); u uuid := gen_random_uuid(); c uuid; n int; BEGIN
  c := (social_wiring.imobshot_obter_ou_criar_card(o, 'ONE3', u)->>'id')::uuid;
  IF social_wiring.imobshot_aplicar_etapa(c, 'fotos_enviadas', NULL, u) THEN RAISE EXCEPTION 'unchanged reported changed'; END IF;
  IF NOT social_wiring.imobshot_aplicar_etapa(c, 'fotos_aprovadas', NULL, NULL) THEN RAISE EXCEPTION 'change not reported'; END IF;
  IF social_wiring.imobshot_aplicar_etapa(c, 'fotos_aprovadas', NULL, u) THEN RAISE EXCEPTION 'repeat reported changed'; END IF;
  SELECT count(*) INTO n FROM social_wiring.imobshot_card_events
   WHERE entity_id = c AND event_type = 'etapa_mudou' AND from_state = 'fotos_enviadas' AND to_state = 'fotos_aprovadas'
     AND actor_id IS NULL AND actor_kind = 'system';
  IF n <> 1 THEN RAISE EXCEPTION 'etapa_mudou=%', n; END IF;
  IF (SELECT etapa FROM social_wiring.imobshot_cards WHERE id = c) <> 'fotos_aprovadas' THEN
    RAISE EXCEPTION 'etapa not written by the primitive'; END IF;
  IF (SELECT fotos_concluidas_at FROM social_wiring.imobshot_cards WHERE id = c) IS NULL THEN
    RAISE EXCEPTION 'fotos_concluidas_at not set'; END IF;
  BEGIN PERFORM social_wiring.imobshot_aplicar_etapa(c, 'nao_existe', NULL, u); RAISE EXCEPTION 'bad etapa accepted';
  EXCEPTION WHEN check_violation THEN NULL; END;
  SELECT count(*) INTO n FROM social_wiring.imobshot_card_events WHERE entity_id = c;
  IF n <> 2 THEN RAISE EXCEPTION 'events after a refused etapa=%', n; END IF;
END $$;""",
    "events_append_only": """
DO $$ DECLARE o uuid := gen_random_uuid(); c uuid; BEGIN
  c := (social_wiring.imobshot_obter_ou_criar_card(o, 'ONE4', NULL)->>'id')::uuid;
  BEGIN UPDATE social_wiring.imobshot_card_events SET event_type = 'etapa_mudou' WHERE entity_id = c;
        RAISE EXCEPTION 'update accepted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM LIKE 'update accepted' THEN RAISE; END IF; END;
  BEGIN DELETE FROM social_wiring.imobshot_card_events WHERE entity_id = c;
        RAISE EXCEPTION 'delete accepted';
  EXCEPTION WHEN OTHERS THEN IF SQLERRM LIKE 'delete accepted' THEN RAISE; END IF; END;
END $$;""",
    "legacy_table_read_only_and_unwritten": """
DO $$ DECLARE r text; BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF has_table_privilege(r, 'social_wiring.imobshot_eventos', 'INSERT') THEN RAISE EXCEPTION '% can insert into the legacy table', r; END IF;
    IF has_table_privilege(r, 'social_wiring.imobshot_eventos', 'UPDATE') THEN RAISE EXCEPTION '% can update the legacy table', r; END IF;
    IF has_table_privilege(r, 'social_wiring.imobshot_eventos', 'DELETE') THEN RAISE EXCEPTION '% can delete from the legacy table', r; END IF;
  END LOOP;
  IF NOT has_table_privilege('service_role', 'social_wiring.imobshot_eventos', 'SELECT') THEN RAISE EXCEPTION 'service_role cannot read the legacy table'; END IF;
  -- the scenarios above wrote events through the functions: none of them reached the legacy table
  IF (SELECT count(*) FROM social_wiring.imobshot_eventos) <> 5 THEN RAISE EXCEPTION 'something still writes the legacy table'; END IF;
END $$;""",
    "rpcs_service_only": """
DO $$ DECLARE f text; r text; BEGIN
  FOREACH f IN ARRAY ARRAY[
    'social_wiring.imobshot_obter_ou_criar_card(uuid,text,uuid)',
    'social_wiring.imobshot_vincular_lote(uuid,uuid,uuid)',
    'social_wiring.imobshot_aplicar_etapa(uuid,text,uuid,uuid)'] LOOP
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
      IF has_function_privilege(r, f, 'EXECUTE') THEN RAISE EXCEPTION '% can execute %', r, f; END IF;
    END LOOP;
    IF NOT has_function_privilege('service_role', f, 'EXECUTE') THEN RAISE EXCEPTION 'service_role cannot execute %', f; END IF;
  END LOOP;
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF has_table_privilege(r, 'social_wiring.imobshot_card_events', 'SELECT') THEN
      RAISE EXCEPTION '% reads imobshot_card_events', r; END IF;
    IF has_function_privilege(r, 'social_wiring.imobshot_card_history(uuid,jsonb)', 'EXECUTE') THEN
      RAISE EXCEPTION '% can execute the primitive history rpc', r; END IF;
  END LOOP;
  IF has_table_privilege('authenticated', 'social_wiring.imobshot_cards', 'INSERT') THEN
    RAISE EXCEPTION 'authenticated writes imobshot_cards'; END IF;
END $$;""",
}


def _steps(legacy_sql: str, scenarios: dict[str, str]) -> list[dict]:
    steps = mr._steps_for(Path(REPO_ROOT), "social-wiring", {_MIG}, "worktree", {})
    steps = [s for s in steps if s["file"] != "346_imobshot_eventos_contract.sql"]  # the contract step has its own tests below
    at = next(i for i, s in enumerate(steps) if s["product"] == "social-wiring" and s["file"] == _MIG_NAME)
    steps.insert(at, {"product": "social-wiring", "file": "fixture:legacy_history", "sql": legacy_sql, "mode": "file", "twice": False})
    for name, sql in scenarios.items():
        steps.append({"product": "social-wiring", "file": name, "sql": sql, "mode": "file", "twice": False})
    return steps


def _with_rerun(steps: list[dict]) -> list[dict]:
    """345 applied AGAIN after live traffic wrote events of its own: it must be a no-op, not a chain-check failure."""
    sql = (Path(REPO_ROOT) / _MIG).read_text(encoding="utf-8")
    return [*steps, {"product": "social-wiring", "file": "rerun_345_after_traffic", "sql": sql, "mode": "file", "twice": False}]


def test_345_moves_the_legacy_history_and_the_rpcs_behave_on_real_postgres(pglite):
    res = mr._run_harness(_with_rerun(_steps(_LEGACY_OK, _MIGRATED)), 900, None)
    assert res.get("ok"), res
    by_file = {st["file"]: st for st in res["steps"]}
    assert not by_file["fixture:legacy_history"]["failures"], by_file["fixture:legacy_history"]["failures"]
    mig = by_file[_MIG_NAME]
    assert not mig["failures"], mig["failures"]
    assert not by_file["rerun_345_after_traffic"]["failures"], by_file["rerun_345_after_traffic"]["failures"]
    bad = {n: by_file[n]["failures"] for n in _MIGRATED if by_file[n]["failures"]}
    assert not bad, bad


def test_345_aborts_and_keeps_the_old_table_when_a_legacy_row_cannot_be_mapped(pglite):
    # The replay harness applies statement by statement, so statements after the abort still run (a real apply is ONE
    # transaction); the guarantee under test is that no legacy row was copied and the old table was not dropped.
    still_there = {"legacy_table_survived": """
DO $$ BEGIN
  IF to_regclass('social_wiring.imobshot_eventos') IS NULL THEN RAISE EXCEPTION 'old table gone after the abort'; END IF;
  IF to_regclass('social_wiring.imobshot_card_events') IS NOT NULL
     AND (SELECT count(*) FROM social_wiring.imobshot_card_events WHERE data->>'migrated_from' IS NOT NULL) <> 0 THEN RAISE EXCEPTION 'partial copy survived the abort'; END IF;
END $$;"""}
    steps = _steps(_LEGACY_BAD, still_there)
    next(s for s in steps if s["file"] == _MIG_NAME)["twice"] = False
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {st["file"]: st for st in res["steps"]}
    errors = " ".join(str(f.get("error", "")) for f in by_file[_MIG_NAME]["failures"])
    assert "cannot be mapped" in errors, by_file[_MIG_NAME]["failures"]
    assert not by_file["legacy_table_survived"]["failures"], by_file["legacy_table_survived"]["failures"]


# --- 346: the contract step (drop of the legacy table) ----------------------------------------------------------

_MIG_346 = "products/social-wiring/backend/migrations/346_imobshot_eventos_contract.sql"
_MIG_346_NAME = Path(_MIG_346).name


def _steps_346(extra_before_346: list[dict], scenarios: dict[str, str]) -> list[dict]:
    steps = mr._steps_for(Path(REPO_ROOT), "social-wiring", {_MIG, _MIG_346}, "worktree", {})
    at = next(i for i, s in enumerate(steps) if s["product"] == "social-wiring" and s["file"] == _MIG_NAME)
    steps.insert(at, {"product": "social-wiring", "file": "fixture:legacy_history", "sql": _LEGACY_OK, "mode": "file", "twice": False})
    at = next(i for i, s in enumerate(steps) if s["file"] == _MIG_346_NAME)
    for extra in reversed(extra_before_346):
        steps.insert(at, extra)
    for name, sql in scenarios.items():
        steps.append({"product": "social-wiring", "file": name, "sql": sql, "mode": "file", "twice": False})
    return steps


_GONE = {"legacy_objects_gone": """
DO $$ BEGIN
  IF to_regclass('social_wiring.imobshot_eventos') IS NOT NULL THEN RAISE EXCEPTION 'legacy table still there'; END IF;
  IF to_regprocedure('social_wiring.imobshot_eventos_append_only()') IS NOT NULL THEN RAISE EXCEPTION 'legacy function still there'; END IF;
  IF (SELECT count(*) FROM social_wiring.imobshot_card_events) <> 5 THEN RAISE EXCEPTION 'events lost'; END IF;
END $$;"""}


def test_346_drops_the_legacy_table_after_a_lossless_345(pglite):
    steps = _steps_346([], _GONE)
    next(s for s in steps if s["file"] == _MIG_346_NAME)["twice"] = True  # idempotent: a second apply is a no-op
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {st["file"]: st for st in res["steps"]}
    assert not by_file[_MIG_346_NAME]["failures"], by_file[_MIG_346_NAME]["failures"]
    assert not by_file["legacy_objects_gone"]["failures"], by_file["legacy_objects_gone"]["failures"]


# A legacy row that never reached the events (e.g. written after 345 by an owner role): must never be dropped.
_UNMIGRATED = {"product": "social-wiring", "file": "fixture:unmigrated_row", "mode": "file", "twice": False, "sql": """
INSERT INTO social_wiring.imobshot_eventos (id, org_id, card_id, tipo, etapa_para, at)
SELECT '00000000-0000-0000-0000-0000000e0099', org_id, id, 'card_criado', 'fotos_enviadas', now()
  FROM social_wiring.imobshot_cards LIMIT 1;"""}

_KEPT = {"legacy_table_survived_the_guard": """
DO $$ BEGIN
  IF to_regclass('social_wiring.imobshot_eventos') IS NULL THEN RAISE EXCEPTION 'unmigrated legacy table was dropped'; END IF;
  IF NOT EXISTS (SELECT 1 FROM social_wiring.imobshot_eventos WHERE id = '00000000-0000-0000-0000-0000000e0099') THEN
    RAISE EXCEPTION 'unmigrated row lost'; END IF;
END $$;"""}


def test_346_refuses_to_drop_a_legacy_row_that_is_not_in_the_events(pglite):
    steps = _steps_346([_UNMIGRATED], _KEPT)
    next(s for s in steps if s["file"] == _MIG_346_NAME)["twice"] = False
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {st["file"]: st for st in res["steps"]}
    errors = " ".join(str(f.get("error", "")) for f in by_file[_MIG_346_NAME]["failures"])
    assert "not in imobshot_card_events" in errors, by_file[_MIG_346_NAME]["failures"]
    assert not by_file["legacy_table_survived_the_guard"]["failures"], by_file["legacy_table_survived_the_guard"]["failures"]
