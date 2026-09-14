-- ============================================================================
-- Migration 110 -- social_wiring: estado civil / regime de bens extraction
-- suggestions, a certidão de nascimento document type
--
-- WHAT THIS IS
-- ------------
-- Migration 097 gave `clientes.estado_civil` / `.regime_bens` real columns and
-- an operator can type them (`ClientePatchBody`). What it did NOT give them is
-- what `cpf` / `rg` already had from day one: a place for the EXTRACTOR's own
-- reading to sit before a human decides whether to trust it. Contract
-- automation F3's seed side (`noctusai_lib.integrations.documents.
-- civil_status`) now returns both fields on `IdentityFields`, closed
-- snake_case vocabulary, averbação-precedence parser — the product side had
-- nowhere on `cliente_documentos` to record what it read.
--
-- Same shape `097` gave `cpf`/`rg`'s readings, copied verbatim rather than
-- invented — see that migration's header for the reasoning this one does not
-- repeat: `identidade_extracao_service.CAMPOS` is table-driven, so this is a
-- pair of triples on `cliente_documentos` plus a pair of provenance quintets
-- on `clientes`, and the apply/suggest/confirm/access-log code path is
-- unchanged.
--
-- 🔴 `estado_civil` / `regime_bens` ARE `sobrescreve=False` (first-writer /
-- first-EXTRACTOR wins), FOR THE SAME REASON `cpf`/`rg` ARE
-- --------------------------------------------------------------------------
-- Neither has a second column holding "what the operator typed" the way
-- `nome_oficial` has `nome_completo` beside it. Overwriting an operator's
-- entry with a later document's reading would destroy it with no way back,
-- so a later reading that disagrees with an existing value lands as a
-- suggestion instead of an overwrite. See `identidade_extracao_service.CAMPOS`
-- for where that policy actually lives (code, not this migration).
--
-- WHY THIS IS NOT A NEW CHECKLIST ITEM
-- -------------------------------------
-- `documento_checklist_service.ITENS` is described, in its own file, as "a
-- contract, not a default" — its exact list and ORDER is a product decision,
-- pinned by a test that reads "the fields the user asked for, in order".
-- `estado_civil` / `regime_bens` therefore ride the existing
-- `sugestoes_extras` mechanism (the same one `nome_oficial` already uses)
-- rather than silently growing that list from this migration. Contract-level
-- completeness (which fields a signed instrument needs from a party, and
-- whether a married party's cônjuge is linked and qualified) is a stricter,
-- separate question, answered by `documento_checklist_service.
-- completude_contratual`.
--
-- WHY `certidao_nascimento` NEEDS ITS OWN TYPE, THE SAME WAY 103 ARGUED
-- -----------------------------------------------------------------------
-- Brazilian civil registries record marriage, divorce and death as
-- AVERBAÇÕES on the birth certificate margin too, not only on a certidão de
-- casamento. `identidade_extracao_service.deve_extrair` gates on the type, so
-- until this row exists a certidão de nascimento filed as `outro` is never
-- scheduled for extraction — a second reachable source of `estado_civil`
-- sitting unread, for the identical reason 103 gave for `certidao_casamento`.
--
-- It joins `TIPOS_LEITURA_INTEGRAL` (code, not this migration) for the same
-- reason: the averbação is prose further into the document, and truncating a
-- civil-registry certidão does not lose detail, it inverts the answer — see
-- 103's header and `civil_status.py`'s module docstring.
--
-- LGPD: `identidade`, same category as every other document this table's
-- retention policy already covers.
--
-- 🔴 RG == CPF: NO CHECK CONSTRAINT, ON PURPOSE, SAME REASONING AS 097's
-- ------------------------------------------------------------------------
-- `noctusai_lib.integrations.documents.rg.is_same_as_cpf` is the guard for
-- "the same eleven digits landed in both boxes" — a qualificação form bug,
-- not a malformed value on its own. It is enforced in CODE, not a database
-- constraint: existing rows may already carry this mistake, and a CHECK
-- would refuse every future write to a row a CHECK never asked about when it
-- was created (the same argument 097 made for leaving `cpf` unique-free).
-- `clientes_service.update_cliente` refuses a manual PATCH that would create
-- or perpetuate the collision (422); `identidade_extracao_service.
-- _aplicar_ao_cliente` declines to APPLY an extracted `rg` that collides with
-- the party's `cpf`, leaving it as a suggestion instead — the reading is not
-- discarded, only not written unattended.
--
-- This migration does not attempt a backfill or a repair pass; it is a
-- read-only accounting question that belongs to whoever operates the live
-- database, not to a forward-only schema change. The query below is a
-- COMMENT, never executed by this file:
--
--   SELECT count(*) AS linhas_afetadas
--   FROM social_wiring.clientes
--   WHERE cpf IS NOT NULL
--     AND rg IS NOT NULL
--     AND social_wiring.normalizar_documento(rg)
--       = social_wiring.normalizar_documento(cpf);
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. The extractor's per-document readings for estado_civil and regime_bens
-- ----------------------------------------------------------------------------
-- Held on the DOCUMENT row, not on the client — same reasoning 097 gave for
-- the cpf/rg triples: a suggestion is not a fact, and it needs somewhere to
-- sit without touching the person's record until a human (or a high-
-- confidence unattended write) says otherwise.
ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_estado_civil            TEXT,
    ADD COLUMN IF NOT EXISTS extracao_estado_civil_confianca  TEXT,
    ADD COLUMN IF NOT EXISTS extracao_estado_civil_rotulo     TEXT,
    ADD COLUMN IF NOT EXISTS extracao_regime_bens             TEXT,
    ADD COLUMN IF NOT EXISTS extracao_regime_bens_confianca   TEXT,
    ADD COLUMN IF NOT EXISTS extracao_regime_bens_rotulo      TEXT;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_estado_civil IS
    'Estado civil as read off THIS document, normalised to the closed '
    'snake_case vocabulary in noctusai_lib.integrations.documents.civil_status'
    '.ESTADO_CIVIL_VALORES. Promoted to clientes.estado_civil only at high '
    'confidence and only when the client has no value yet — see '
    'identidade_extracao_service.CAMPOS (sobrescreve=False).';
COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_regime_bens IS
    'Regime de bens as read off THIS document. Vocabulary: civil_status.'
    'REGIME_BENS_VALORES. Same write policy as extracao_estado_civil.';

-- ----------------------------------------------------------------------------
-- 2. Provenance quintets on `clientes`, mirroring the cpf/rg shape from 097
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS estado_civil_origem          TEXT,
    ADD COLUMN IF NOT EXISTS estado_civil_documento_id    UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS estado_civil_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS estado_civil_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS estado_civil_confirmado_em   TIMESTAMPTZ,

    ADD COLUMN IF NOT EXISTS regime_bens_origem            TEXT,
    ADD COLUMN IF NOT EXISTS regime_bens_documento_id      UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS regime_bens_em                TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS regime_bens_confirmado_por    UUID,
    ADD COLUMN IF NOT EXISTS regime_bens_confirmado_em     TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.estado_civil_origem IS
    '''manual'' | ''rg'' | ''cpf'' | ''cnh'' | ''certidao_casamento'' | '
    '''certidao_nascimento'' -- where the CURRENT estado_civil value came '
    'from. NULL alongside a non-null estado_civil means it predates 110.';
COMMENT ON COLUMN social_wiring.clientes.estado_civil_confirmado_por IS
    'Set when a human accepted a LOW-confidence read. NULL alongside a set '
    'estado_civil means the extractor wrote it unattended at high '
    'confidence, or an operator typed it directly (origem=''manual'').';
COMMENT ON COLUMN social_wiring.clientes.regime_bens_origem IS
    'Same contract as estado_civil_origem, for regime_bens.';

-- Pending-suggestion lookup, widened to also catch estado_civil/regime_bens
-- readings — same predicate 097 built for cpf/rg, on the same index. Dropped
-- and recreated rather than altered in place: PostgreSQL has no
-- ALTER INDEX ... WHERE, and this keeps the definition in one CREATE
-- statement instead of a partial index nobody can read as a whole.
DROP INDEX IF EXISTS social_wiring.idx_sw_cliente_documentos_sugestao_doc_pendente;
CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_sugestao_doc_pendente
    ON social_wiring.cliente_documentos (cliente_id, extracao_em DESC)
    WHERE deleted_at IS NULL
      AND extracao_descartada_em IS NULL
      AND (
          extracao_cpf IS NOT NULL
          OR extracao_rg IS NOT NULL
          OR extracao_estado_civil IS NOT NULL
          OR extracao_regime_bens IS NOT NULL
      );

-- ----------------------------------------------------------------------------
-- 3. `certidao_nascimento` as a first-class document type
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.cliente_documento_tipos
    (tipo_documento, categoria_lgpd, descricao, ativo)
VALUES
    ('certidao_nascimento', 'identidade',
     'Certidão de nascimento (com averbações) — estado civil e regime de '
     'bens podem estar averbados na margem',
     TRUE)
ON CONFLICT (tipo_documento) DO UPDATE
    SET categoria_lgpd = EXCLUDED.categoria_lgpd,
        descricao      = EXCLUDED.descricao,
        ativo          = TRUE;
