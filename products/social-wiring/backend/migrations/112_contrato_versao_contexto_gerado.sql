-- ============================================================================
-- Migration 112 · social_wiring: the rendering snapshot of a GENERATED version
--
-- Migration 106 created `atendimento_contrato_versoes.origem` with 'gerado'
-- already allowed, so the F5 generator (card_hub/contrato_gerador) could land
-- additively. This file adds the ONE column that generation needs and an
-- upload does not: a SHA-256 of the exact data the document was rendered from.
--
-- WHY A HASH AND NOT THE CONTEXT ITSELF
-- --------------------------------------------------------------------------
-- The rendering context names CPF/RG, bank accounts and the literal matrícula
-- text of every party. Storing it again, beside the .docx that already
-- carries it, would double the personal-data footprint of every generated
-- version for no read path anybody has. What the spec needs (§5.2 #18,
-- "card vs contract") is to answer "has the card changed since this version
-- was generated?" — recomputing the hash from the card's current state and
-- comparing answers that without keeping a second copy.
--
-- WHY THE CHECK
-- --------------------------------------------------------------------------
-- A 'gerado' version without its snapshot is exactly the drift this column
-- exists to detect, silently undetectable; an 'upload' with one would claim a
-- provenance it does not have. The CHECK pins both directions. Every row
-- existing before this migration is an upload with a NULL here, so the
-- constraint validates immediately.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.atendimento_contrato_versoes
    ADD COLUMN IF NOT EXISTS contexto_sha256 TEXT;

COMMENT ON COLUMN social_wiring.atendimento_contrato_versoes.contexto_sha256 IS
    'SHA-256 (hex) of the canonical JSON of the data a gerado version was '
    'rendered from. NULL for uploads. See migration 112 header.';

ALTER TABLE social_wiring.atendimento_contrato_versoes
    DROP CONSTRAINT IF EXISTS atendimento_contrato_versoes_contexto_por_origem;
ALTER TABLE social_wiring.atendimento_contrato_versoes
    ADD CONSTRAINT atendimento_contrato_versoes_contexto_por_origem
    CHECK (
        (origem = 'gerado' AND contexto_sha256 ~ '^[0-9a-f]{64}$')
        OR (origem = 'upload' AND contexto_sha256 IS NULL)
    );
