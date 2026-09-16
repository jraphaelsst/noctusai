-- ============================================================================
-- Migration 117 -- social_wiring: data de casamento, data de emissão da
-- certidão, e as respostas operacionais do escritório (contract F6)
--
-- WHAT THIS IS
-- ------------
-- Three independent additions the office's own answers required, landing
-- together because all three came out of the same qualification-gap review:
--
-- 1. `clientes.data_casamento` -- the marriage CELEBRATION date. The
--    office's generated instrument cites Lei 6.515/77 differently depending
--    on which side of 26/12/1977 this date falls, and until now nothing on
--    a `casado` cliente recorded it at all.
-- 2. `cliente_documentos.extracao_data_emissao` -- the certidão's OWN
--    issuance date ("emitida em" / the cartório's closing line). Answers
--    the office's second rule: a certidão de estado civil must be under 90
--    days old AS OF SIGNING. Read off `certidao_casamento` AND
--    `certidao_nascimento` alike -- see `noctusai_lib.integrations.
--    documents.civil_status.find_data_emissao`.
-- 3. `org_dados_cadastrais` operational settings -- the signing platform
--    name/URL, the daily holdover ("posse") fine, and the default
--    pendências window. Not extracted from anything; the office typed
--    these answers directly.
--
-- 🔴 `data_casamento` IS A CAMPO, `data_emissao` IS NOT
-- --------------------------------------------------------------------------
-- Same shape 097/110 established for cpf/rg/estado_civil/regime_bens, and
-- the same asymmetry `rg_orgao` already carries: `data_casamento` is a fact
-- about the HOLDER (promotable to `clientes`, first-writer-wins like
-- `data_nascimento` -- see `identidade_extracao_service.CAMPOS`), while
-- `data_emissao` is a fact about the DOCUMENT (one certidão, one issuance
-- date -- a person's several certidões each have their own, so there is no
-- `clientes` column for it to promote to). See
-- `noctusai_lib.integrations.documents.types.IdentityFields`'s own
-- docstring for the full reasoning.
--
-- FORWARD-ONLY, IDEMPOTENT (safe to re-run; every step is existence-guarded).
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. clientes.data_casamento -- the CAMPO, provenance quintet mirrors 097/110
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS data_casamento DATE,

    ADD COLUMN IF NOT EXISTS data_casamento_origem          TEXT,
    ADD COLUMN IF NOT EXISTS data_casamento_documento_id    UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS data_casamento_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS data_casamento_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS data_casamento_confirmado_em   TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.data_casamento IS
    'The marriage CELEBRATION date, off a certidão de casamento -- decides '
    'which side of Lei 6.515/77''s 26/12/1977 line the generated instrument '
    'cites. First-writer-wins (sobrescreve=False), same posture as '
    'data_nascimento -- see identidade_extracao_service.CAMPOS.';
COMMENT ON COLUMN social_wiring.clientes.data_casamento_origem IS
    '''manual'' | ''certidao_casamento'' -- where the CURRENT data_casamento '
    'value came from. NULL alongside a non-null data_casamento predates 117.';
COMMENT ON COLUMN social_wiring.clientes.data_casamento_confirmado_por IS
    'Set when a human accepted a LOW-confidence read. NULL alongside a set '
    'data_casamento means the extractor wrote it unattended at high '
    'confidence, or an operator typed it directly (origem=''manual'').';

-- ----------------------------------------------------------------------------
-- 2. cliente_documentos -- the extractor's own readings, data_casamento AND
--    the document-scoped (never promoted) data_emissao
--
-- 🔴 ORDER MATTERS: these columns are added BEFORE the partial index below,
-- whose predicate names `extracao_data_casamento`. The first version of this
-- file rebuilt that index in section 1, ahead of the ALTER that creates the
-- column, and failed on the live database with
-- `42703: column "extracao_data_casamento" does not exist` (2026-09-16).
-- The whole script rolled back, so nothing was half-applied — but the file
-- was unrunnable against ANY database, and the suite never caught it because
-- `test_migration_*` asserts on the SQL TEXT and never executes it.
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_data_casamento            DATE,
    ADD COLUMN IF NOT EXISTS extracao_data_casamento_confianca  TEXT,
    ADD COLUMN IF NOT EXISTS extracao_data_casamento_rotulo     TEXT,

    -- Never promoted to clientes -- see the header's asymmetry note.
    ADD COLUMN IF NOT EXISTS extracao_data_emissao              DATE,
    ADD COLUMN IF NOT EXISTS extracao_data_emissao_confianca    TEXT,
    ADD COLUMN IF NOT EXISTS extracao_data_emissao_rotulo       TEXT;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_data_casamento IS
    'Marriage celebration date as read off THIS certidão. Promoted to '
    'clientes.data_casamento only at high confidence and only when the '
    'client has no value yet -- see identidade_extracao_service.CAMPOS '
    '(sobrescreve=False).';
COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_data_emissao IS
    'This certidão''s OWN issuance date ("emitida em" / the cartório''s '
    'closing line) -- a fact about the DOCUMENT, not the holder. Never '
    'promoted to clientes; read back by identidade_extracao_service.'
    'certidao_estado_civil_mais_recente for the office''s 90-day-freshness '
    'rule. Populated for both certidao_casamento and certidao_nascimento.';

-- Pending-suggestion lookup, widened to also catch data_casamento readings
-- -- same predicate 110 built for estado_civil/regime_bens, same index.
-- Rebuilt HERE, after the ALTER above, because its predicate names
-- `extracao_data_casamento` (see the section header).
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
          OR extracao_data_casamento IS NOT NULL
      );

-- Freshness lookup: the client's certidões, newest emission first. Partial
-- on the two document types that carry this field, same reasoning the
-- sugestão-pendente index above gives for its own WHERE clause.
CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_certidao_emissao
    ON social_wiring.cliente_documentos (cliente_id, extracao_data_emissao DESC)
    WHERE deleted_at IS NULL
      AND extracao_descartada_em IS NULL
      AND tipo_documento IN ('certidao_casamento', 'certidao_nascimento')
      AND extracao_data_emissao IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. org_dados_cadastrais -- the office's operational settings
-- ----------------------------------------------------------------------------
-- Every OTHER column on this table is nullable (100's own header: "a
-- settings form someone fills in over several sittings"). `prazo_
-- pendencias_padrao_dias` breaks that pattern on purpose: it is not
-- cadastral data awaiting completion, it is an operational THRESHOLD other
-- code may read to compute a due date, and a NULL there pushes the "what do
-- I default to" question onto every future reader instead of answering it
-- once, here, with the office's own stated default of 10 days.
ALTER TABLE social_wiring.org_dados_cadastrais
    ADD COLUMN IF NOT EXISTS plataforma_assinatura_nome     TEXT,
    ADD COLUMN IF NOT EXISTS plataforma_assinatura_url      TEXT,
    ADD COLUMN IF NOT EXISTS posse_multa_diaria             NUMERIC,
    ADD COLUMN IF NOT EXISTS prazo_pendencias_padrao_dias    INTEGER
        NOT NULL DEFAULT 10;

ALTER TABLE social_wiring.org_dados_cadastrais
    DROP CONSTRAINT IF EXISTS org_dados_cadastrais_posse_multa_diaria_nao_negativa;
ALTER TABLE social_wiring.org_dados_cadastrais
    ADD CONSTRAINT org_dados_cadastrais_posse_multa_diaria_nao_negativa
    CHECK (posse_multa_diaria IS NULL OR posse_multa_diaria >= 0);

ALTER TABLE social_wiring.org_dados_cadastrais
    DROP CONSTRAINT IF EXISTS org_dados_cadastrais_prazo_pendencias_positivo;
ALTER TABLE social_wiring.org_dados_cadastrais
    ADD CONSTRAINT org_dados_cadastrais_prazo_pendencias_positivo
    CHECK (prazo_pendencias_padrao_dias > 0);

COMMENT ON COLUMN social_wiring.org_dados_cadastrais.plataforma_assinatura_nome IS
    'The e-signature platform''s name (e.g. "ClickSign"), printed on the '
    'generated instrument''s signature clause. The office''s own answer.';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.plataforma_assinatura_url IS
    'The e-signature platform''s URL. HTTPS-only, enforced at the API '
    'boundary (DadosImobiliariaBody) rather than here: a CHECK re-deriving '
    'URL-scheme validation in SQL would be a second, driftable copy of the '
    'same rule.';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.posse_multa_diaria IS
    'R$/day fine for a holdover after the contractual "posse" deadline. '
    'NULLABLE -- unlike prazo_pendencias_padrao_dias, there is no safe '
    'platform-wide default for a monetary penalty; a form left blank means '
    '"not set", not "R$ 0".';
COMMENT ON COLUMN social_wiring.org_dados_cadastrais.prazo_pendencias_padrao_dias IS
    'Default window (days) a "pendência" gets before it counts as overdue. '
    'NOT NULL DEFAULT 10 -- the office''s own stated default; see the '
    'section header for why this one column is not nullable like its '
    'siblings.';
