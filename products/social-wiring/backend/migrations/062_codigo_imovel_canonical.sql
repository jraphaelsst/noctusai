-- ============================================================================
-- Migration 062 -- social_wiring: canonical property codes
--
-- THE BUG
-- -------
-- `leads.codigo_imovel` is free TEXT compared literally against
-- `imoveis.codigo`. The XLSX importer's `parse_codigo` returns the regex
-- match VERBATIM (`[A-Za-z]{1,4}\d{3,6}` — case-insensitive, no `.upper()`),
-- so whatever the operator typed is what landed. Measured on the live tenant
-- 2026-08-20:
--
--   leads with a código           11375
--   resolve against the mirror     1699   (14.9%)
--   resolve ONLY case-insensitively 2406   (21.1%)  <- silently lost today
--   genuine orphans                7270   (63.9%)  <- see migration 063
--
-- 6057 rows carry a lowercase character somewhere. `One10107` and `ONE10107`
-- are the same imóvel and have never joined.
--
-- The drift is PURELY case. Verified, not assumed:
--   · rows with leading/trailing whitespace .... 0
--   · rows with internal whitespace ............ 0
--   · rows failing ^[A-Z]{1,4}[0-9]{3,6}$ ...... 0
-- So the canonical form is exactly `upper(btrim(...))`. Nothing is being
-- guessed, parsed, or repaired — only case-folded.
--
-- THE SHAPE: raw stays, derived column joins
-- ------------------------------------------
-- Deliberately NOT an in-place UPDATE of `codigo_imovel`. This mirrors
-- `canonicalize_lead_contato()` (migration 037) exactly, and for the same
-- reason: the original spelling stays in `codigo_imovel`, so the backfill is
-- reversible with no extra column and no information is destroyed. `leads`
-- already carries `origem_raw` / `corretor_raw` under the same convention —
-- raw in, derived beside it.
--
-- WHY NOT A SHAPE FILTER
-- ----------------------
-- An earlier draft NULLed `codigo_imovel_norm` when the value failed the
-- `^[A-Z]{2,4}[0-9]{3,6}$` product-code pattern, matching `contato_norm`'s
-- "nothing may key on a value we had to guess". Dropped: case-folding guesses
-- NOTHING, so there is no unsafe value to withhold. Shape validation belongs
-- at ingress (the Python parser), not in a derivation that would silently hide
-- a one-letter-prefix code like `P0601` from the very query a human would use
-- to find it.
--
-- PREREQUISITE: 025_leads.sql, 040_imoveis.sql.
-- Forward-only + idempotent (IF NOT EXISTS / DROP..CREATE on the trigger).
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.
-- ============================================================================

SET search_path = social_wiring, public;

-- ── PART A -- the mirror side ───────────────────────────────────────────
-- `codigo` is a plain column on this table, so a STORED generated column is
-- available and is strictly better than a trigger: Postgres itself guarantees
-- it can never drift from its input, and there is no write path to forget.
ALTER TABLE social_wiring.imoveis
    ADD COLUMN IF NOT EXISTS codigo_norm TEXT
    GENERATED ALWAYS AS (upper(btrim(codigo))) STORED;

-- UNIQUE, not just an index. The census found zero duplicate `codigo` within
-- the tenant, and case-folding cannot create a collision that the PK
-- `(org_id, codigo)` did not already permit — unless two rows differ ONLY by
-- case, which would mean Vista is serving the same imóvel twice. If that ever
-- happens the sync must fail loudly here rather than silently upsert one row
-- over the other.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_imoveis_org_codigo_norm
    ON social_wiring.imoveis (org_id, codigo_norm);

-- ── PART B -- the leads side ────────────────────────────────────────────
-- A trigger, not a generated column: `leads` is written by five paths (XLSX
-- import, WhatsApp intake, OLX + imovelweb webhooks, Meta lead forms) and a
-- generated column would be equivalent here — but the trigger form matches
-- 037's established shape for this table, and PART C's backfill needs to run
-- against rows the generated-column ALTER would rewrite anyway.
ALTER TABLE social_wiring.leads
    ADD COLUMN IF NOT EXISTS codigo_imovel_norm TEXT;

COMMENT ON COLUMN social_wiring.leads.codigo_imovel_norm IS
  'Case-folded join key for social_wiring.imoveis.codigo_norm. Derived by '
  'canonicalize_lead_codigo_imovel_trigger for EVERY write path. NULL means '
  'the row carries no código at all — never that one was rejected. The '
  'original spelling always remains in codigo_imovel.';

CREATE OR REPLACE FUNCTION social_wiring.canonicalize_lead_codigo_imovel()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
  v_value TEXT;
BEGIN
  v_value := btrim(COALESCE(NEW.codigo_imovel, ''));

  IF v_value = '' THEN
    NEW.codigo_imovel_norm := NULL;
  ELSE
    NEW.codigo_imovel_norm := upper(v_value);
  END IF;

  RETURN NEW;
END
$$;

-- `UPDATE OF codigo_imovel` and not a bare `UPDATE`: re-deriving on every
-- unrelated PATCH is wasted work, and a derived column cannot go stale while
-- its only input is unchanged. Same rule as 037's trigger.
DROP TRIGGER IF EXISTS canonicalize_lead_codigo_imovel_trigger ON social_wiring.leads;
CREATE TRIGGER canonicalize_lead_codigo_imovel_trigger
  BEFORE INSERT OR UPDATE OF codigo_imovel ON social_wiring.leads
  FOR EACH ROW EXECUTE FUNCTION social_wiring.canonicalize_lead_codigo_imovel();

-- ── PART C -- backfill the 11375 existing rows ──────────────────────────
-- Guarded on `IS DISTINCT FROM` so a re-run is a no-op rather than a full
-- table rewrite. `codigo_imovel` is never written.
UPDATE social_wiring.leads
   SET codigo_imovel_norm = upper(btrim(codigo_imovel))
 WHERE codigo_imovel IS NOT NULL
   AND btrim(codigo_imovel) <> ''
   AND codigo_imovel_norm IS DISTINCT FROM upper(btrim(codigo_imovel));

-- ── PART D -- the join index ────────────────────────────────────────────
-- Partial: 2030 of 13405 leads carry no código, and they can never satisfy
-- this join.
CREATE INDEX IF NOT EXISTS idx_sw_leads_org_codigo_norm
    ON social_wiring.leads (org_id, codigo_imovel_norm)
    WHERE codigo_imovel_norm IS NOT NULL;

-- ── PART E -- lead_vendas, same treatment ───────────────────────────────
-- Empty today (0 rows), but it carries the same `codigo_imovel TEXT` column
-- and would reproduce the identical bug the moment it is written to. Fixing
-- it now costs nothing; fixing it after it holds history costs another
-- backfill.
ALTER TABLE social_wiring.lead_vendas
    ADD COLUMN IF NOT EXISTS codigo_imovel_norm TEXT;

CREATE OR REPLACE FUNCTION social_wiring.canonicalize_venda_codigo_imovel()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  SET search_path TO 'social_wiring', 'public'
AS $$
DECLARE
  v_value TEXT;
BEGIN
  v_value := btrim(COALESCE(NEW.codigo_imovel, ''));
  NEW.codigo_imovel_norm := CASE WHEN v_value = '' THEN NULL ELSE upper(v_value) END;
  RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS canonicalize_venda_codigo_imovel_trigger ON social_wiring.lead_vendas;
CREATE TRIGGER canonicalize_venda_codigo_imovel_trigger
  BEFORE INSERT OR UPDATE OF codigo_imovel ON social_wiring.lead_vendas
  FOR EACH ROW EXECUTE FUNCTION social_wiring.canonicalize_venda_codigo_imovel();

UPDATE social_wiring.lead_vendas
   SET codigo_imovel_norm = upper(btrim(codigo_imovel))
 WHERE codigo_imovel IS NOT NULL
   AND btrim(codigo_imovel) <> ''
   AND codigo_imovel_norm IS DISTINCT FROM upper(btrim(codigo_imovel));

CREATE INDEX IF NOT EXISTS idx_sw_lead_vendas_org_codigo_norm
    ON social_wiring.lead_vendas (org_id, codigo_imovel_norm)
    WHERE codigo_imovel_norm IS NOT NULL;
