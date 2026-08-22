-- ============================================================================
-- Migration 068 · social_wiring: the identity substrate + a DERIVED checklist
--
-- WHY THIS EXISTS
-- ---------------
-- Migration 067 shipped the six-item document checklist as tick-state. What it
-- could not ship — because the columns did not exist — is the DATA those ticks
-- are about. `clientes` carries `nome`, `chave_canonica`/`chave_tipo` and
-- lifecycle columns; there is no `data_nascimento`, no `genero`, no `email`
-- anywhere in this schema. So four of the six items have been human-ticked
-- assertions with nothing behind them, and "this client's data is complete"
-- has been unfalsifiable.
--
-- This migration adds the substrate and, in the same change, flips the
-- checklist from STORED state to DERIVED state.
--
-- 🔴 WHY DERIVED, AND NOT A RECOMPUTE HOOK
-- ----------------------------------------
-- The obvious build is a hook: on cliente insert/update and on document
-- upload, recompute the six ticks and write them. It is wrong for one
-- structural reason — leads enter this product from Meta leadgen, OLX,
-- ImovelWeb, Vista, the XLSX importer, the manual lead form, and the
-- merge/undo path in `clientes_service`, and each of those is a separate
-- write site that must remember to call the hook. The one that forgets does
-- not fail loudly; it leaves a checklist that is quietly out of date, which is
-- indistinguishable from a client who genuinely has not sent their documents.
--
-- Derived state cannot drift, because there is no interval during which it is
-- allowed to be stale. A path added tomorrow is covered the day it lands, with
-- no wiring. That is the same argument 067 itself made for keeping the
-- checklist DEFINITION in code, applied one column further.
--
-- What genuinely IS per-client is a human OVERRIDE — "I confirmed their gender
-- verbally, tick it even though the column is empty". So the tick column
-- survives, with narrowed meaning: NULL = follow the derivation, true/false =
-- a human forced it.
--
-- LOSSLESS: every existing row in `cliente_documento_checklist` was written by
-- `documento_checklist_service.marcar()` — the only writer that has ever
-- existed for this table — so every existing row IS an explicit human action
-- and is preserved verbatim as an override, false ones included.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the row
-- counts this will touch and the user has given an explicit go-ahead.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. clientes — the identity substrate the checklist describes
-- ----------------------------------------------------------------------------
-- `nome_completo` is deliberately SEPARATE from the existing `nome`. `nome` is
-- whatever the originating channel supplied — a WhatsApp push name, a Meta
-- leadgen `full_name`, an OLX display name — and is frequently a first name, a
-- nickname, or a handle. The checklist item is "Nome Completo", a distinct
-- assertion that someone has collected the person's legal full name. Folding
-- them would auto-tick that item for every lead that ever arrived with any
-- name at all, which is precisely the false-completeness this migration exists
-- to remove.
--
-- `email` is its own column rather than a read of `chave_canonica`: that key
-- holds EITHER a phone or an email (`chave_tipo` decides), so a phone-keyed
-- cliente — the majority — has nowhere to put an email today.
--
-- `genero` is unconstrained TEXT on purpose. A CHECK here would freeze a
-- gender taxonomy as a schema decision made by whoever wrote this migration;
-- it is a product decision, and the checklist only needs to know whether the
-- field was filled in.
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS nome_completo   TEXT,
    ADD COLUMN IF NOT EXISTS email           TEXT,
    ADD COLUMN IF NOT EXISTS data_nascimento DATE,
    ADD COLUMN IF NOT EXISTS genero          TEXT;

-- Provenance for the ONE field this product can fill in automatically.
--
-- Without this you cannot tell a birthdate a human typed from one an OCR pass
-- inferred off a photographed RG, and the two do not deserve equal trust: the
-- plausibility gate in the extractor rejects a year of 1830 or a date in 2027,
-- but it cannot catch 1980 misread as 1930. Both are plausible ages. Storing
-- the origin is what keeps such a value attributable and correctable instead
-- of becoming an anonymous fact in a column.
--
-- `data_nascimento_origem` values: 'manual' | 'rg' | 'cpf' | 'cnh' | 'import'.
-- Left as TEXT rather than a CHECK so a new ingestion channel does not need a
-- migration to name itself.
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS data_nascimento_origem      TEXT,
    ADD COLUMN IF NOT EXISTS data_nascimento_documento_id UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS data_nascimento_em          TIMESTAMPTZ;

-- ----------------------------------------------------------------------------
-- 2. cliente_documento_checklist — tick becomes an OVERRIDE, not the truth
-- ----------------------------------------------------------------------------
-- Renamed rather than shadowed by a second column: two columns where one is
-- authoritative is exactly the ambiguity this change removes, and a stale
-- `concluido` that nothing reads would be read by someone eventually.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'social_wiring'
          AND table_name   = 'cliente_documento_checklist'
          AND column_name  = 'concluido'
    ) THEN
        ALTER TABLE social_wiring.cliente_documento_checklist
            RENAME COLUMN concluido TO concluido_manual;
    END IF;
END $$;

-- NULL is now meaningful — "no human has an opinion; use the derivation" —
-- so the NOT NULL and the DEFAULT both have to go. A DEFAULT of false would
-- silently mean "a human said no" for every row inserted from now on.
ALTER TABLE social_wiring.cliente_documento_checklist
    ALTER COLUMN concluido_manual DROP DEFAULT;
ALTER TABLE social_wiring.cliente_documento_checklist
    ALTER COLUMN concluido_manual DROP NOT NULL;

COMMENT ON COLUMN social_wiring.cliente_documento_checklist.concluido_manual IS
    'Human override. NULL = derive from the cliente record + uploaded '
    'documents (the normal case). true/false = a person forced this tick '
    'and their decision outranks the derivation.';

-- ----------------------------------------------------------------------------
-- 3. cliente_documentos — the extraction result, held ON the document
-- ----------------------------------------------------------------------------
-- The document row IS the provenance, so the extraction result lives here
-- rather than on `clientes`. It also gives low-confidence reads somewhere to
-- sit WITHOUT touching the client record: a suggestion the card can offer for
-- confirmation is not the same thing as a stored fact, and conflating them is
-- how a guess becomes someone's birthday.
ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_status     TEXT
        CHECK (extracao_status IN ('pendente', 'processando', 'ok', 'sem_dados', 'erro')),
    ADD COLUMN IF NOT EXISTS extracao_em         TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS extracao_data_nascimento DATE,
    -- 'alta' | 'baixa' | 'nenhuma' — mirrors
    -- noctusai_lib.integrations.documents.ExtractionConfidence.
    ADD COLUMN IF NOT EXISTS extracao_confianca  TEXT,
    -- 'texto' (PDF text layer, exact) | 'ocr' (rasterize→vision, approximate).
    ADD COLUMN IF NOT EXISTS extracao_fonte      TEXT,
    -- The label the date was found next to, verbatim. Lets a human audit the
    -- extractor's reasoning without RE-READING the document — which would
    -- itself be another logged content access.
    ADD COLUMN IF NOT EXISTS extracao_rotulo     TEXT,
    ADD COLUMN IF NOT EXISTS extracao_erro       TEXT;

-- The background worker's claim path: every identity document not yet read.
CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_extracao_pendente
    ON social_wiring.cliente_documentos (extracao_status)
    WHERE deleted_at IS NULL AND extracao_status IN ('pendente', 'processando');

-- ----------------------------------------------------------------------------
-- 4. cliente_documento_acessos — an automated read is still a read
-- ----------------------------------------------------------------------------
-- Extraction opens the file's bytes, so under 057's contract ("every read of a
-- document's CONTENT appends to the access log") it MUST append. Logging it as
-- 'view' with a null usuario_id was the tempting shortcut and is the wrong
-- one: it launders a machine read as a human one and makes the log unable to
-- answer "who looked at this person's RG?" — the exact question the log exists
-- for.
ALTER TABLE social_wiring.cliente_documento_acessos
    DROP CONSTRAINT IF EXISTS cliente_documento_acessos_acao_check;
ALTER TABLE social_wiring.cliente_documento_acessos
    ADD CONSTRAINT cliente_documento_acessos_acao_check
    CHECK (acao IN ('view', 'download', 'delete', 'extract'));

-- ----------------------------------------------------------------------------
-- 5. NOT DONE HERE, ON PURPOSE: enabling the rg/cpf document types
-- ----------------------------------------------------------------------------
-- `cliente_documento_tipos` still seeds 'rg' and 'cpf' with `ativo = false`
-- (migration 057), so `documentos_service` refuses them and the extraction
-- path above is unreachable in production. That is deliberate and this
-- migration does NOT change it.
--
-- The open LGPD data-category intake at LGPD-WARNINGS.md (filed 2026-08-18)
-- gates that flip, and extraction makes the intake MORE load-bearing rather
-- than less: deriving a birthdate from an identity document is a new
-- processing purpose over sensitive data, distinct from merely storing the
-- file, and the intake has to name it. Enabling the types stays a data change
-- made by a human after that intake resolves — never a deploy, and never an
-- agent's decision.
