-- ============================================================================
-- Migration 054 -- social_wiring: collapse `negociacoes_venda` duplicate
-- pairs into one Funil card per human (lead-card-hub P1.4 completion)
--
-- lead-card-hub roadmap (`project-history/roadmaps/lead-card-hub-2026-08.md`
-- §1, §5 Phase 1 P1.4) + contract `products/social-wiring/projects/
-- lead-card-hub-p1-PROJECT.md`. `048` added `negociacoes_venda.cliente_id`
-- and retired `negociacoes_venda_exactly_one_origin`, and the backfill
-- repoints every row at its resolved `cliente`. Neither step COLLAPSES
-- anything: a Meta lead still fires BOTH `spawn_funil_card_on_lead` (via
-- `ingest_meta_lead` writing `leads`) and `spawn_funil_card_on_meta_lead`
-- (writing `meta_ads_leads` directly) for the SAME human, so it still gets
-- TWO cards on `/api/funil` -- measured 2026-08-07: 125 duplicate pairs,
-- 100% forward rate on every new Meta lead. This file is the missing step.
--
-- WHAT THIS FILE DOES
-- --------------------
-- 1. Adds `negociacoes_venda.substituida_por` (self-FK, nullable) +
--    `colapsada_em` (timestamptz, nullable). A collapsed card is MARKED,
--    never deleted -- reversible by nulling these two columns alone, no
--    reconstruction needed, matching D3's undo bar for `cliente_merges`.
-- 2. Two indexes serving the two read shapes the pipeline module needs:
--    "give me this org's still-visible cards" (`substituida_por IS NULL`)
--    and "give me everything folded into this survivor" (`substituida_por
--    = <id>`, used to assemble the DTO's `colapsadas` list).
-- 3. A data step that collapses every EXISTING set of `negociacoes_venda`
--    rows sharing a `cliente_id` into one survivor. Idempotent: it only
--    ever considers rows with `substituida_por IS NULL`, so an
--    already-collapsed row drops out of the grouping on re-run and a
--    second run of this file is a no-op against unchanged data.
--
-- WHAT THIS FILE DOES NOT DO
-- ---------------------------
-- It does not handle a NEW duplicate created AFTER this migration applies
-- -- that is `clientes_backfill_job`'s job (the exact "one-shot backfill
-- against a table that keeps growing is a snapshot, not a projection"
-- lesson `048`'s OWN backfill already ran into once, commit `7db51307`).
-- `clientes_service._collapse_negociacoes` mirrors this file's survivor
-- rule in Python so the 6-hourly steady-state sweep collapses new pairs
-- automatically, not only at this one-shot moment.
--
-- THE SURVIVOR RULE -- an interpretation call, surfaced explicitly
-- --------------------------------------------------------------------
-- The roadmap's own words for P1.4: "keeping the furthest-advanced stage".
-- Read literally across EVERY row sharing a `cliente_id` regardless of
-- `status`, that rule has a failure mode this file does not accept: a
-- `negociacao` that reached a late stage before being marked `perdida`
-- (lost) would then outrank a genuinely NEW, currently-`aberta` (open)
-- negociação for the same person -- and since the Funil board
-- (`obter_funil`) only ever shows `status = 'aberta'` cards, collapsing
-- the open one BEHIND the closed one would make it vanish from the board
-- entirely. That is a strictly worse outcome than the duplicate this
-- migration exists to fix (`KB § PATTERNS/frontend/lying-loading-state.md`'s
-- sibling principle, applied to disappearing rather than lying: a card
-- that silently disappears is worse than one that is silently doubled).
--
-- The survivor is therefore chosen by, in order:
--   1. `status = 'aberta'` beats any closed status -- an open deal is
--      never hidden behind a closed one, full stop;
--   2. among rows of the same openness, the FURTHEST-ADVANCED STAGE wins,
--      derived from THIS ORG's own `pipeline_stages.posicao` for the
--      `funil` pipeline -- never a hardcoded stage-slug list, because
--      stages are user-editable rows (migration `034`'s whole point);
--   3. tie-break: the OLDEST `created_at` (deterministic -- the earlier
--      card is the one more likely to already carry follow-up notes /
--      stage history worth keeping visible);
--   4. final tie-break: the lower `id` (UUIDs never collide, so this
--      always terminates the ordering).
--
-- At the live scale this migration was designed against -- `negociacoes_
-- venda` has existed only since `034` landed this same cycle, so there is
-- no reason to expect a closed-vs-open collision inside a single duplicate
-- set today -- but the rule above is written to be correct if that ever
-- changes, rather than correct only by the current data's good luck.
--
-- FORWARD-ONLY, IDEMPOTENT, matching every migration in this product.
-- 🔴 Applying this (like `048`, `050`) is the tech-lead's + user's decision,
-- not this file's -- see contract §7. The engineer who wrote this did NOT
-- have a database to verify it against; see the delivery note for how far
-- verification could go without one.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. The collapse columns
-- ----------------------------------------------------------------------------
-- Self-referential, ON DELETE SET NULL: a collapsed row losing its survivor
-- (an edge-case hard delete) must become independently visible again rather
-- than vanish along with a row it never owned any data of its own inside.
ALTER TABLE social_wiring.negociacoes_venda
    ADD COLUMN IF NOT EXISTS substituida_por UUID
        REFERENCES social_wiring.negociacoes_venda(id) ON DELETE SET NULL;

ALTER TABLE social_wiring.negociacoes_venda
    ADD COLUMN IF NOT EXISTS colapsada_em TIMESTAMPTZ;

-- "Give me this org's still-visible cards, grouped by person" -- the exact
-- shape `app/modules/pipeline/routers/boards.py::obter_funil` queries.
CREATE INDEX IF NOT EXISTS idx_sw_negociacoes_venda_cliente_ativa
    ON social_wiring.negociacoes_venda (org_id, cliente_id)
    WHERE substituida_por IS NULL;

-- "Give me everything folded into this survivor" -- powers the DTO's
-- `colapsadas` list (`app/modules/pipeline/configs.py::attach_colapsadas`)
-- and admin/audit lookups. Partial on IS NOT NULL: a non-collapsed row
-- (the overwhelming majority) never needs to appear in this index.
CREATE INDEX IF NOT EXISTS idx_sw_negociacoes_venda_substituida
    ON social_wiring.negociacoes_venda (substituida_por)
    WHERE substituida_por IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 2. The one-shot collapse of the 125 existing duplicate pairs (and any
--    other set already sharing a cliente_id)
-- ----------------------------------------------------------------------------
DO $$
DECLARE
  v_collapsed INTEGER;
BEGIN
  WITH candidatos AS (
    SELECT
      nv.id,
      nv.cliente_id,
      nv.status,
      nv.created_at,
      -- COALESCE, not an INNER JOIN: `etapa_id` is a NOT NULL FK to
      -- `pipeline_stages`, so this should always match -- the fallback is
      -- pure defensive posture, not an expected path, and it deliberately
      -- ranks a row whose stage lookup somehow failed LAST rather than
      -- erroring the whole migration over one row.
      COALESCE(ps.posicao, -1) AS posicao
    FROM social_wiring.negociacoes_venda nv
    LEFT JOIN social_wiring.pipeline_stages ps ON ps.id = nv.etapa_id
    WHERE nv.cliente_id IS NOT NULL
      AND nv.substituida_por IS NULL
  ),
  ranqueadas AS (
    SELECT
      id,
      cliente_id,
      ROW_NUMBER() OVER (
        PARTITION BY cliente_id
        ORDER BY
          (status = 'aberta') DESC,  -- rule 1: open beats closed
          posicao DESC,              -- rule 2: furthest-advanced stage wins
          created_at ASC,            -- rule 3: oldest wins ties
          id ASC                     -- rule 4: final deterministic tiebreak
      ) AS rn,
      COUNT(*) OVER (PARTITION BY cliente_id) AS grupo_tamanho
    FROM candidatos
  ),
  sobreviventes AS (
    SELECT cliente_id, id AS sobrevivente_id
    FROM ranqueadas
    WHERE rn = 1
  ),
  a_colapsar AS (
    SELECT r.id, s.sobrevivente_id
    FROM ranqueadas r
    JOIN sobreviventes s USING (cliente_id)
    WHERE r.rn > 1 AND r.grupo_tamanho > 1
  )
  UPDATE social_wiring.negociacoes_venda nv
  SET substituida_por = a.sobrevivente_id,
      colapsada_em = now()
  FROM a_colapsar a
  WHERE nv.id = a.id;

  GET DIAGNOSTICS v_collapsed = ROW_COUNT;
  RAISE NOTICE
    'migration 054: collapsed % negociacoes_venda row(s) into their '
    'furthest-advanced, still-open sibling', v_collapsed;
END
$$;

NOTIFY pgrst, 'reload schema';
