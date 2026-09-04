-- ============================================================================
-- Migration 098 -- social_wiring: o lado VENDEDOR do atendimento
--
-- WHAT THIS IS
-- ------------
-- One column. `atendimento_partes` already models "a person party to a deal,
-- in a role" and everything downstream of it — the checklist, the uploads, the
-- extraction, the access log, the LGPD retention — works on a `cliente_id`
-- and does not care which side of the table that person sits on. What was
-- missing was the SIDE.
--
-- 🔴 WHY A SIDE, AND NOT MORE `papel` VALUES
-- -------------------------------------------
-- The tempting cheap move is to keep one flat vocabulary and add `vendedor`,
-- `vendedor_conjuge`, `vendedor_procurador` next to `comprador`, `conjuge`,
-- `procurador`. It is cheap exactly once. `conjuge` and `procurador` mean the
-- same thing on both sides — they are the same relationship to a different
-- principal — so a flat list has to prefix half its members and then every
-- reader parses the prefix back off to answer "whose spouse?". That is a
-- composite key spelled as a string.
--
-- Side and role are two independent facts, so they are two columns:
--
--     lado  = comprador | vendedor      -- which side of the deal
--     papel = proprietario | conjuge | procurador | fiador | ...  -- what they
--                                          are TO that side
--
-- `papel` stays unconstrained TEXT, as migration 073 left it and for the
-- reason 074 spelled out: a new role should not need a migration. The
-- per-side vocabulary is validated in `compradores_service`, next to the
-- dropdown that offers it.
--
-- 🔴 WHY THE DEFAULT IS 'comprador' AND WHY THAT IS NOT A COINCIDENCE DEFAULT
-- ---------------------------------------------------------------------------
-- Every existing row IS a comprador-side party: migration 073 created this
-- table to hold co-buyers, the service's `PAPEL_PADRAO` is `comprador`, and
-- no writer has ever put a seller in it. So the default backfills the whole
-- table correctly with no UPDATE, and it stays the right answer afterwards
-- because the buyer side is where a party is added by default from a lead's
-- card. The seller side is always chosen explicitly.
--
-- 🔴 THE PESSOA-UNIQUENESS INDEX IS LEFT ALONE, DELIBERATELY
-- -----------------------------------------------------------
-- `uq_sw_atendimento_partes_pessoa` is UNIQUE (atendimento_id, cliente_id) —
-- so one person cannot appear twice on one atendimento, INCLUDING once per
-- side. Widening it to include `lado` would permit somebody to be both buyer
-- and seller of the same property, which is not a deal. Keeping it narrow is
-- what makes that unrepresentable.
--
-- THE TITULAR IS STILL NOT IN HERE, on the buyer side
-- ---------------------------------------------------
-- `atendimentos.lead_id` / `cliente_id` names the buyer-side titular, and
-- migration 073's header explains why a second row asserting it would be a
-- second truth. The seller side has NO such column, so every seller-side party
-- lives here — the first one (`ordem = 0`, `papel = 'proprietario'`) being the
-- owner the deal is with. That asymmetry is real and is not worth erasing: the
-- buyer arrives as a lead and the seller does not arrive at all.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimento_partes
    ADD COLUMN IF NOT EXISTS lado TEXT NOT NULL DEFAULT 'comprador';

COMMENT ON COLUMN social_wiring.atendimento_partes.lado IS
    'comprador | vendedor — which side of the negotiation this person is on. '
    'Independent of `papel`, which says what they are TO that side. See the '
    '098 header for why these are two columns and not one prefixed string.';

COMMENT ON COLUMN social_wiring.atendimento_partes.papel IS
    'The person''s role within their `lado`: proprietario | conjuge | '
    'procurador | fiador | inventariante | outro. Unconstrained TEXT — the '
    'per-side vocabulary lives in compradores_service beside the dropdown, so '
    'a new role needs no migration.';

-- The board reads one side at a time, in display order. The existing
-- `idx_sw_atendimento_partes_atendimento` covers (atendimento_id, ordem) and
-- stays — this one is the side-filtered read the two panels actually issue.
CREATE INDEX IF NOT EXISTS idx_sw_atendimento_partes_lado
    ON social_wiring.atendimento_partes (atendimento_id, lado, ordem);

-- ----------------------------------------------------------------------------
-- `vinculo_origem` gains its seller-side value
-- ----------------------------------------------------------------------------
-- Migration 074 made `clientes.vinculo_origem` TEXT rather than a CHECK
-- precisely so a new relationship path needed no migration, and this is that
-- path arriving. Nothing to ALTER — the note is here so the next reader
-- greping for `vendedor_atendimento` finds where it was introduced.
COMMENT ON COLUMN social_wiring.clientes.vinculo_origem IS
    'How the link was made — ''comprador_atendimento'' | '
    '''vendedor_atendimento'' (migration 098). TEXT rather than a CHECK so a '
    'new relationship path needs no migration.';
