-- ============================================================================
-- Migration 073 · social_wiring: the parties to an atendimento + two more
--                 checklist fields
--
-- WHAT THIS IS FOR
-- ----------------
-- An atendimento has always been modelled as one person: the lead becomes a
-- cliente, the cliente gets a card, the card carries the checklist and the
-- documents. That is correct right up to the moment the buyer is married.
--
-- A buy/sell agency contract needs the SPOUSE's identity data and the
-- SPOUSE's documents, to the same standard and for the same reason. Today
-- there is nowhere to put them: the checklist keys off `cliente_id`, the
-- documents key off `cliente_id`, and an atendimento has exactly one.
--
-- So this migration adds the join that lets an atendimento have more than one
-- person attached, plus the two identity fields the checklist was missing.
--
-- 🔴 WHY A COMPRADOR IS A `clientes` ROW, NOT A NEW KIND OF RECORD
-- ----------------------------------------------------------------
-- The tempting build is a lightweight `atendimento_partes` table carrying its
-- own nome/celular/email columns — "it's just the spouse, they don't need the
-- full treatment". They do, and that is the whole point: the spouse needs the
-- SAME eight checklist items and the SAME RG/CPF uploads as the titular,
-- because the contract asks the same things of both.
--
-- Giving them their own columns means a second document table, a second
-- checklist table, a second access log, a second extraction path — the entire
-- card_hub stack forked for person #2, and every fix to one half silently not
-- applying to the other. That is the replication-to-seed slip in its most
-- expensive form.
--
-- A comprador is therefore a `clientes` row like any other, and this table is
-- only the EDGE: which people are party to which atendimento, and in what
-- role. Everything downstream — checklist, documents, extraction, the access
-- log, LGPD retention — already works on a `cliente_id` and needs no change
-- to cover the second person. The spouse who already exists as a lead is
-- LINKED rather than duplicated, which is a correctness win the fork could
-- not have offered at any price.
--
-- 🔴 WHY THE TITULAR IS NOT A ROW HERE
-- ------------------------------------
-- The symmetric-looking move is to give every atendimento a row for its own
-- titular too, so "the parties" is one list. It is rejected for two reasons.
--
-- First, `atendimentos.lead_id` ALREADY names the titular, and has since
-- migration 054. A second place that also names them is a second truth, and
-- the two disagree the first time either is written without the other.
--
-- Second, it would need a backfill across every existing atendimento, and a
-- backfill that half-runs leaves cards whose party list is missing its own
-- subject — a card that does not know whose it is.
--
-- So: the titular is the atendimento's own lead. This table holds the
-- ADDITIONAL parties. The UI renders the titular first and these after, which
-- is what it was going to do regardless of how they were stored.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the row
-- counts this will touch and the user has given an explicit go-ahead.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. clientes.profissao + clientes.celular — the checklist's new fields
-- ----------------------------------------------------------------------------
-- `profissao` is plain operator-entered TEXT. Unlike `data_nascimento` and
-- `nome_oficial` it is NOT derived from an identity document — an RG does not
-- carry a profession — so it needs no provenance triplet. If a future channel
-- starts supplying it (Vista's `Profissao` field is the obvious candidate; see
-- LGPD-WARNINGS.md), THAT is when provenance columns earn their place.
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS profissao TEXT;

COMMENT ON COLUMN social_wiring.clientes.profissao IS
    'Declared profession. Operator-entered only — no extraction path writes '
    'this column. Checklist item `profissao` derives its tick from it.';

-- `celular` is the exact mirror of what 068 did for `email`, and for the same
-- reason stated there. `chave_canonica` holds EITHER a phone or an email and
-- `chave_tipo` decides which — so a phone-keyed cliente already has their
-- number (the majority case, and the one the user means by "it comes from the
-- registration act"), but an EMAIL-keyed cliente has nowhere to put a phone at
-- all.
--
-- That gap stops being cosmetic with this change, because celular becomes a
-- REQUIRED field: an atendimento cannot leave its stage without one. A
-- requirement that some clientes are structurally unable to satisfy is not a
-- requirement, it is a trap.
--
-- 🔴 This does NOT duplicate `chave_canonica`. The checklist reads `celular`
-- FIRST and falls back to the canonical key only when it is phone-typed, so
-- the explicit operator entry always wins and the derived one covers everyone
-- else — the same precedence `nome_completo` uses over `nome`. Nothing writes
-- both, and `chave_canonica` remains the identity key it has always been.
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS celular TEXT;

COMMENT ON COLUMN social_wiring.clientes.celular IS
    'Explicit phone number, for clientes whose canonical key is an email (or '
    'who have none). The checklist prefers this over chave_canonica; a '
    'phone-keyed cliente normally leaves it NULL and ticks off the key.';

-- ----------------------------------------------------------------------------
-- 2. genero — provenance, because it is now read off the RG
-- ----------------------------------------------------------------------------
-- `genero` itself arrived with migration 068 as a plain column, fillable by an
-- operator. It is now ALSO derivable from an identity document, which makes it
-- the third extracted field after `data_nascimento` (068) and `nome_oficial`
-- (071) — and extraction without provenance is how a machine guess becomes an
-- anonymous fact on someone's record.
--
-- Same five-column shape as `nome_oficial`, and deliberately so: the shape is
-- what `identidade_extracao_service.CampoExtraido` derives its column names
-- from, so a field that matches the convention needs no special-casing
-- anywhere in the extraction, suggestion or confirmation paths.
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS genero_origem          TEXT,
    ADD COLUMN IF NOT EXISTS genero_documento_id    UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS genero_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS genero_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS genero_confirmado_em   TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.genero IS
    'Gender. Operator-entered, or read off an identity document when the '
    'extractor is confident. Deliberately unconstrained TEXT (see 068) — the '
    'UI offers Masculino/Feminino, but the taxonomy is a product decision, '
    'not a schema one.';

COMMENT ON COLUMN social_wiring.clientes.genero_origem IS
    '''manual'' | ''rg'' | ''cpf'' | ''cnh'' | ''import'' — where this value '
    'came from. NULL alongside a non-null genero means it predates 073.';

COMMENT ON COLUMN social_wiring.clientes.genero_confirmado_por IS
    'Set when a human accepted a LOW-confidence read. NULL with origem=''rg'' '
    'means the extractor was confident enough to write it unattended.';

-- The document side: what was read, how sure, and off which label.
ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_genero           TEXT,
    ADD COLUMN IF NOT EXISTS extracao_genero_confianca TEXT,
    ADD COLUMN IF NOT EXISTS extracao_genero_rotulo    TEXT;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_genero IS
    'Gender as read off THIS document. Held on the document row so a '
    'low-confidence read has somewhere to sit without touching the client '
    'record — a suggestion is not a fact.';

-- ----------------------------------------------------------------------------
-- 3. atendimento_partes — the edge
-- ----------------------------------------------------------------------------
-- `papel` is unconstrained TEXT and validated in the service layer against a
-- code-owned tuple, for the same reason `documento_checklist_service.ITENS`
-- lives in code: the set of roles is a product decision that will grow
-- (cônjuge, fiador, procurador), and freezing it in a CHECK means a migration
-- every time the business learns a new word. The service refuses an unknown
-- papel with a 422, so the constraint is enforced — just not by the schema.
CREATE TABLE IF NOT EXISTS social_wiring.atendimento_partes (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    atendimento_id UUID NOT NULL
        REFERENCES social_wiring.atendimentos(id) ON DELETE CASCADE,
    -- ON DELETE CASCADE, not SET NULL: a parte with no person is not a
    -- degraded row, it is a meaningless one.
    cliente_id     UUID NOT NULL
        REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    papel          TEXT NOT NULL DEFAULT 'comprador',
    -- Display order within the atendimento. Not a rank — the titular is not
    -- in this table at all, so 0 is simply "first of the additional parties".
    ordem          INTEGER NOT NULL DEFAULT 0,
    observacao     TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by     UUID,
    updated_at     TIMESTAMPTZ
);

-- One row per (atendimento, person). Adding the same spouse twice is a
-- double-click, not an intent, and the service's insert relies on this to say
-- so with a 409 rather than silently growing the list.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_atendimento_partes_pessoa
    ON social_wiring.atendimento_partes (atendimento_id, cliente_id);

CREATE INDEX IF NOT EXISTS idx_sw_atendimento_partes_atendimento
    ON social_wiring.atendimento_partes (atendimento_id, ordem);

-- Answers "which atendimentos is this person party to?" — the question the
-- Clientes detail view asks when it shows someone who is a spouse on one deal
-- and a titular on another.
CREATE INDEX IF NOT EXISTS idx_sw_atendimento_partes_cliente
    ON social_wiring.atendimento_partes (org_id, cliente_id);

ALTER TABLE social_wiring.atendimento_partes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "atendimento_partes_select_own_org"
    ON social_wiring.atendimento_partes;
CREATE POLICY "atendimento_partes_select_own_org"
    ON social_wiring.atendimento_partes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "atendimento_partes_service_role"
    ON social_wiring.atendimento_partes;
CREATE POLICY "atendimento_partes_service_role"
    ON social_wiring.atendimento_partes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE social_wiring.atendimento_partes IS
    'Additional people party to an atendimento beyond its titular (who is '
    'named by atendimentos.lead_id). Each references a full clientes row, so '
    'the document checklist, uploads and extraction cover them unchanged.';
