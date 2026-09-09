-- ============================================================================
-- Migration 104 · social_wiring: a visita can generate a PROPOSTA, and one of
-- those propostas gets ACCEPTED. That accepted one is the imóvel of the deal.
--
-- WHAT THIS CLOSES
-- ----------------
-- The owner's sentence, which the schema could not hold until now: a roteiro
-- carries N candidate imóveis (082); one of them generates a proposta; the
-- proposta that gets ACCEPTED is the imóvel that attaches to the atendimento
-- and feeds the contract automation.
--
-- `atendimento_negociacao.imovel_codigo` (077) is the deal's property and has
-- existed since that migration — but nothing in the schema said HOW a código
-- got there. It was a field an operator typed into, with no link back to the
-- visit that produced the offer. So "which of the six properties we showed
-- them did they actually buy, and when did we learn that" was unanswerable
-- from the data, and the funil stage was the only trace.
--
-- ── 🔴 WHY THIS IS NOT A FOURTH `status` VALUE ────────────────────────────
-- `visitas.status` answers exactly one question: **did the visit happen?**
-- 082's header is explicit that it holds three values rather than a boolean
-- because "hasn't happened yet" and "didn't happen" are different facts and
-- collapsing them files every future visit under "did not".
--
-- "A proposta came from this one" is an ORTHOGONAL axis. A visita that
-- generated a proposta is still a visita that HAPPENED — that is in fact the
-- only kind that can generate one. Adding `proposta` to the enum would
-- overwrite the did-it-happen fact the moment an offer appears, and the
-- contabilização 082 exists for ("visitas that happened and the ones that
-- didn't") would silently start under-counting `realizada` by exactly the
-- visits that went best. The value would be unrecoverable: nothing else in
-- the row remembers it.
--
-- Two axes, two sets of columns. `status` keeps its three values, forever.
--
-- ── 🔴 WHY ACCEPTANCE IS RECORDED PER-VISITA, NOT ONLY AS A FUNIL STAGE ───
-- The funil stage says the DEAL advanced. It cannot say WHICH property caused
-- it, and that is the fact the contract automation consumes: the roteiro is a
-- list of candidates and the stage is one flag over the whole atendimento.
-- Recorded per-visita, the chain is legible end to end — this route, this
-- property, this offer, this acceptance, this contract — and it stays legible
-- years later, which is the same durability requirement 082 was built for.
--
-- It also gives the two moments separate timestamps. "We made an offer" and
-- "they accepted it" are different events, days apart, and a single boolean
-- would lose the gap that every commission forecast is built on.
--
-- ── WHY THE CHECK, AND WHY ONLY THIS ONE ──────────────────────────────────
-- `proposta_aceita_em IS NULL OR proposta_em IS NOT NULL` — an acceptance
-- with no offer is not a state that exists in the world, and letting it into
-- the table would make "propostas made" smaller than "propostas accepted" in
-- every report drawn off these columns.
--
-- What is deliberately NOT constrained here: "at most one accepted proposta
-- per ATENDIMENTO". It is a real rule and it is enforced in
-- `roteiros_service` — see that module. A UNIQUE index cannot express it,
-- because the scope is the atendimento and these rows are keyed to a
-- ROTEIRO; the join `visitas → roteiros → atendimentos` is two hops away and
-- a partial unique index cannot traverse it. Naming the absence here so the
-- next reader knows it was decided rather than forgotten.
--
-- PREREQUISITE: 082_roteiros_visitas.sql, 077_atendimento_negociacao.sql.
-- Forward-only + idempotent. Purely additive — no existing row changes, and
-- every new column is nullable, so this is a no-op for live data.
-- ============================================================================

SET search_path = social_wiring, public;

-- ── The proposta axis ───────────────────────────────────────────────────
ALTER TABLE social_wiring.visitas
    ADD COLUMN IF NOT EXISTS proposta_em          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS proposta_por         UUID,
    ADD COLUMN IF NOT EXISTS proposta_aceita_em   TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS proposta_aceita_por  UUID;

COMMENT ON COLUMN social_wiring.visitas.proposta_em IS
    'A proposta was generated from this visita. NULL means none. An axis '
    'ORTHOGONAL to `status` — a visita that produced an offer is still a '
    'visita that happened, and folding this into the status enum would '
    'destroy the contabilização migration 082 exists for.';

COMMENT ON COLUMN social_wiring.visitas.proposta_por IS
    'Who recorded the proposta. A USER id, resolved against '
    'public.noctus_users like every other actor column in this schema — '
    'never a free-text name.';

COMMENT ON COLUMN social_wiring.visitas.proposta_aceita_em IS
    'That proposta was ACCEPTED. THIS is the imóvel of the deal: the service '
    'writes this visita''s `codigo` into '
    '`atendimento_negociacao.imovel_codigo` for the owning atendimento. At '
    'most one accepted proposta per atendimento — enforced in '
    '`roteiros_service`, not by a constraint (see this migration''s header).';

COMMENT ON COLUMN social_wiring.visitas.proposta_aceita_por IS
    'Who recorded the acceptance.';

-- An acceptance with no offer is not a state that exists in the world.
ALTER TABLE social_wiring.visitas
    DROP CONSTRAINT IF EXISTS visitas_proposta_aceita_exige_proposta;
ALTER TABLE social_wiring.visitas
    ADD CONSTRAINT visitas_proposta_aceita_exige_proposta
    CHECK (proposta_aceita_em IS NULL OR proposta_em IS NOT NULL);

-- Reading "which visita is the accepted one" is the hot path — the card asks
-- it on every render of the Negociação panel and the contract automation asks
-- it per atendimento. Partial: the overwhelming majority of visitas never
-- carry a proposta, and indexing those rows would be index bloat for nothing.
CREATE INDEX IF NOT EXISTS idx_sw_visitas_proposta_aceita
    ON social_wiring.visitas (org_id, roteiro_id)
    WHERE proposta_aceita_em IS NOT NULL;
