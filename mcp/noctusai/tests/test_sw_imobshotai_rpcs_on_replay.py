"""Social-wiring 343 (ImobShotAI) on REAL Postgres (PGlite, the migration-replay harness): the migration applies twice,
and the three service-only functions behave as the repository relies on. Each scenario is a DO block that RAISES on any
deviation, so a step with no failures is a pass.

Scope note: PostgREST's `fotos_lotes!inner(criado_por)` embed (the corretor board filter) cannot run on PGlite; the
test runs the equivalent SQL (an inner join/EXISTS on `fotos_lotes.card_id`) and asserts a card appears once even when
the corretor created several of its lotes. Concurrency is modelled by the second call hitting the unique key."""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_MIG = "products/social-wiring/backend/migrations/343_imobshotai_cards.sql"

_SCENARIOS = {
    "obter_ou_criar_idempotent": """
DO $$ DECLARE o uuid := gen_random_uuid(); u uuid := gen_random_uuid(); a jsonb; b jsonb; n int; BEGIN
  a := social_wiring.imobshot_obter_ou_criar_card(o, 'ONE1', u);
  b := social_wiring.imobshot_obter_ou_criar_card(o, 'ONE1', u);
  IF NOT (a->>'criado')::boolean OR (b->>'criado')::boolean OR a->>'id' <> b->>'id' THEN
    RAISE EXCEPTION 'not idempotent: % %', a, b; END IF;
  SELECT count(*) INTO n FROM social_wiring.imobshot_cards WHERE org_id = o;
  IF n <> 1 THEN RAISE EXCEPTION 'cards=%', n; END IF;
  SELECT count(*) INTO n FROM social_wiring.imobshot_eventos WHERE org_id = o AND tipo = 'card_criado';
  IF n <> 1 THEN RAISE EXCEPTION 'card_criado=%', n; END IF;
END $$;""",
    "vincular_lote_atomic": """
DO $$ DECLARE o uuid := gen_random_uuid(); u uuid := gen_random_uuid(); c uuid; l uuid; other uuid; n int; ok boolean; BEGIN
  c := (social_wiring.imobshot_obter_ou_criar_card(o, 'ONE2', u)->>'id')::uuid;
  INSERT INTO social_wiring.fotos_lotes (org_id, nome, criado_por, origem, velocidade)
    VALUES (o, 'x', u, 'vista', 'urgente') RETURNING id INTO l;
  ok := social_wiring.imobshot_vincular_lote(c, l, u);
  IF NOT ok THEN RAISE EXCEPTION 'link refused'; END IF;
  IF (SELECT card_id FROM social_wiring.fotos_lotes WHERE id = l) <> c THEN RAISE EXCEPTION 'card_id not set'; END IF;
  SELECT count(*) INTO n FROM social_wiring.imobshot_eventos
   WHERE card_id = c AND tipo = 'lote_vinculado' AND detalhe->>'lote_id' = l::text;
  IF n <> 1 THEN RAISE EXCEPTION 'lote_vinculado=%', n; END IF;
  -- linking again is a no-op (no second event); another org's lote is refused
  IF social_wiring.imobshot_vincular_lote(c, l, u) THEN RAISE EXCEPTION 'relink wrote'; END IF;
  INSERT INTO social_wiring.fotos_lotes (org_id, nome, criado_por, origem, velocidade)
    VALUES (gen_random_uuid(), 'y', u, 'vista', 'urgente') RETURNING id INTO other;
  IF social_wiring.imobshot_vincular_lote(c, other, u) THEN RAISE EXCEPTION 'cross-org link accepted'; END IF;
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
  IF NOT social_wiring.imobshot_aplicar_etapa(c, 'fotos_aprovadas', NULL, u) THEN RAISE EXCEPTION 'change not reported'; END IF;
  IF social_wiring.imobshot_aplicar_etapa(c, 'fotos_aprovadas', NULL, u) THEN RAISE EXCEPTION 'repeat reported changed'; END IF;
  SELECT count(*) INTO n FROM social_wiring.imobshot_eventos
   WHERE card_id = c AND tipo = 'etapa_mudou' AND etapa_de = 'fotos_enviadas' AND etapa_para = 'fotos_aprovadas';
  IF n <> 1 THEN RAISE EXCEPTION 'etapa_mudou=%', n; END IF;
  IF (SELECT fotos_concluidas_at FROM social_wiring.imobshot_cards WHERE id = c) IS NULL THEN
    RAISE EXCEPTION 'fotos_concluidas_at not set'; END IF;
  BEGIN PERFORM social_wiring.imobshot_aplicar_etapa(c, 'nao_existe', NULL, u); RAISE EXCEPTION 'bad etapa accepted';
  EXCEPTION WHEN check_violation THEN NULL; END;
END $$;""",
    "eventos_append_only": """
DO $$ DECLARE o uuid := gen_random_uuid(); c uuid; BEGIN
  c := (social_wiring.imobshot_obter_ou_criar_card(o, 'ONE4', NULL)->>'id')::uuid;
  BEGIN UPDATE social_wiring.imobshot_eventos SET tipo = 'card_arquivado' WHERE card_id = c;
        RAISE EXCEPTION 'update accepted';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN DELETE FROM social_wiring.imobshot_eventos WHERE card_id = c;
        RAISE EXCEPTION 'delete accepted';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
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
  IF has_table_privilege('authenticated', 'social_wiring.imobshot_eventos', 'SELECT') THEN
    RAISE EXCEPTION 'authenticated reads imobshot_eventos'; END IF;
  IF has_table_privilege('authenticated', 'social_wiring.imobshot_cards', 'INSERT') THEN
    RAISE EXCEPTION 'authenticated writes imobshot_cards'; END IF;
END $$;""",
}


def test_343_applies_twice_and_the_rpcs_behave_on_real_postgres(pglite):
    steps = mr._steps_for(Path(REPO_ROOT), "social-wiring", {_MIG}, "worktree", {})
    for name, sql in _SCENARIOS.items():
        steps.append({"product": "social-wiring", "file": name, "sql": sql, "mode": "file", "twice": False})
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {st["file"]: st for st in res["steps"]}
    mig = by_file[Path(_MIG).name]
    assert not mig["failures"], mig["failures"]
    bad = {n: by_file[n]["failures"] for n in _SCENARIOS if by_file[n]["failures"]}
    assert not bad, bad
