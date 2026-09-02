-- ============================================================================
-- Migration 088 — Backfill `clientes.celular` / `.email` from their sources
--
-- WHY THIS EXISTS
-- ---------------
-- The identity backfill created every cliente WITHOUT ever writing `celular`
-- or `email`: it stored the canonical KEY (`chave_canonica` + `chave_tipo`)
-- and nothing else. Two consequences, both reported from production:
--
--   * The person's card showed "— " for Celular and Email next to a lead whose
--     phone was plainly visible on the board.
--   * `stage_gate` refuses a move until the checklist can tick "Celular". The
--     checklist reads `celular` first and falls back to `chave_canonica` only
--     when `chave_tipo = 'telefone'` — so a KEYLESS cliente (identity could
--     not be resolved, `chave_canonica IS NULL`) had NOTHING to tick and its
--     card could never leave the first column, no matter how complete the
--     underlying lead was.
--
-- The keyless case is not rare: it is every lead whose contact could not be
-- parsed into a canonical key, plus every cluster parked for review. Those are
-- exactly the leads an operator most wants to pick up and work.
--
-- The code fix (`identidade_service.SourceRow.telefone/.email` +
-- `clientes_service._contato_dos_membros` / `_enrich_cliente`) stops this for
-- everything created from now on. This migration repairs the rows that already
-- exist, so nobody has to wait for a touch to arrive.
--
-- 🔴 FILL-IF-EMPTY. Every UPDATE is guarded on the target column being NULL or
-- blank. A value an operator typed by hand outranks anything derived from a
-- lead row and must never be overwritten by this.
--
-- IDEMPOTENT: re-running finds nothing left to fill.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. From `leads`, via `cliente_touches`.
--
-- `contato_norm` is the canonical value (migration 037's trigger) and is
-- preferred; `contato` is the raw fallback for a row that never normalised —
-- which is precisely the keyless case this migration exists for.
-- ---------------------------------------------------------------------------
WITH origem AS (
  SELECT t.cliente_id,
         (array_remove(array_agg(COALESCE(l.contato_norm, l.contato)
            ORDER BY l.created_at) FILTER (WHERE l.contato_tipo = 'telefone'), NULL))[1] AS telefone,
         (array_remove(array_agg(lower(COALESCE(l.contato_norm, l.contato))
            ORDER BY l.created_at) FILTER (WHERE l.contato_tipo = 'email'), NULL))[1] AS email,
         (array_remove(array_agg(l.cliente_nome ORDER BY l.created_at), NULL))[1] AS nome
    FROM social_wiring.cliente_touches t
    JOIN social_wiring.leads l
      ON l.id::text = t.origem_id AND t.origem_tabela = 'leads'
   GROUP BY t.cliente_id
)
UPDATE social_wiring.clientes c
   SET celular = COALESCE(NULLIF(btrim(c.celular), ''), origem.telefone),
       email   = COALESCE(NULLIF(btrim(c.email),   ''), origem.email),
       nome    = COALESCE(NULLIF(btrim(c.nome),    ''), origem.nome)
  FROM origem
 WHERE c.id = origem.cliente_id
   AND (   NULLIF(btrim(c.celular), '') IS NULL
        OR NULLIF(btrim(c.email),   '') IS NULL
        OR NULLIF(btrim(c.nome),    '') IS NULL);

-- ---------------------------------------------------------------------------
-- 2. From `meta_ads_leads`, same shape.
--
-- A campaign lead routinely supplies BOTH a phone and an email; only the phone
-- ever became the key, so the email was dropped entirely.
-- ---------------------------------------------------------------------------
WITH origem AS (
  SELECT t.cliente_id,
         (array_remove(array_agg(m.phone ORDER BY m.created_time), NULL))[1] AS telefone,
         (array_remove(array_agg(lower(m.email) ORDER BY m.created_time), NULL))[1] AS email,
         (array_remove(array_agg(m.full_name ORDER BY m.created_time), NULL))[1] AS nome
    FROM social_wiring.cliente_touches t
    JOIN social_wiring.meta_ads_leads m
      ON m.id::text = t.origem_id AND t.origem_tabela = 'meta_ads_leads'
   GROUP BY t.cliente_id
)
UPDATE social_wiring.clientes c
   SET celular = COALESCE(NULLIF(btrim(c.celular), ''), origem.telefone),
       email   = COALESCE(NULLIF(btrim(c.email),   ''), origem.email),
       nome    = COALESCE(NULLIF(btrim(c.nome),    ''), origem.nome)
  FROM origem
 WHERE c.id = origem.cliente_id
   AND (   NULLIF(btrim(c.celular), '') IS NULL
        OR NULLIF(btrim(c.email),   '') IS NULL
        OR NULLIF(btrim(c.nome),    '') IS NULL);

COMMENT ON COLUMN social_wiring.clientes.celular IS
  'The person''s phone, independent of whether it also became `chave_canonica`. '
  'A keyless cliente still has one; the checklist and `stage_gate` read this '
  'first. Populated by the identity backfill since migration 088.';
