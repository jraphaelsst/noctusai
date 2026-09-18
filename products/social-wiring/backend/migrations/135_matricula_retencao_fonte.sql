-- ============================================================================
-- Migration 135 · social_wiring: the standalone matrícula upload keeps its
-- source PDF, and a re-transcription SUPERSEDES rather than rewrites
--
-- CONTEXT
-- -------
-- `matricula_extracoes` (092) has two upload shapes. The LINKED one (109,
-- `codigo` + `imovel_documento_id`) keeps the PDF as the imóvel's document —
-- `POST /extracoes/de-documento` already re-transcribes it. The UNLINKED
-- shape (092's original design) has never kept the bytes: `service.py`'s
-- `MENSAGEM_ORFA` says so outright ("this workflow keeps no copy of the
-- uploaded PDF"). Verified live 2026-09-17: all 6 prod rows are unlinked, so
-- EVERY existing transcription is unauditable and unrepeatable, and the
-- write-once trigger (111) correctly refuses to let any of them be fixed in
-- place — the only way out was never re-uploading, because there was nothing
-- to re-upload FROM.
--
-- WHAT THIS DOES
-- --------------
-- 1. `matricula_extracao_arquivos` — the unlinked shape's retained PDF,
--    written through the SAME `DocumentoStore` mechanism `imovel_documentos` /
--    `cliente_documentos` / `atendimento_documentos` already use (validate /
--    put / insert / sign / soft-delete). There is no owner narrower than the
--    org for a file that has not been linked to an imóvel — `owner_col =
--    'org_id'` says so explicitly rather than inventing a fake one. LGPD
--    access (view/download of the raw PDF) rides the EXISTING
--    `imovel_document_acessos.extracao_id` column (111) via
--    `documento_store.log_acesso_extracao` — a matrícula's raw bytes are as
--    CPF-bearing as its transcription, and that column already exists for
--    exactly this "no imovel_documentos row" shape. No new access-log table.
-- 2. `matricula_extracoes.arquivo_origem_id` — points an unlinked row at its
--    retained file, the same shape `imovel_documento_id` gives the linked
--    one. At most one of the two is ever set (an extraction is either linked
--    to an imóvel's document or to its own standalone one, never both).
-- 3. `matricula_extracoes.substituida_por` — the supersede pointer,
--    self-referential, the EXACT shape `negociacoes_venda.substituida_por`
--    (054) already established for this platform's "never rewrite, mark and
--    replace" pattern. A re-transcription INSERTS a new row (carrying the
--    same `codigo` / `imovel_documento_id` / `arquivo_origem_id`) and marks
--    the old one — never touches the old row's `texto_extraido`, so the
--    write-once trigger (111) is never in tension with this: a supersede is
--    a NEW row, not a rewritten one. The RESTRICT foreign keys 109/115 put on
--    `matricula_atos` / `matricula_ato_detalhes` /
--    `atendimento_contrato_matricula_atos` / `imovel_dados.titulo_aquisitivo_*`
--    mean a superseded row is NEVER deleted while anything still cites it —
--    superseding leaves it exactly where those citations expect it.
-- 4. `matricula_extracoes.possui_marcacao_bruta` — legible, queryable flag
--    for the 5 markered rows `NOC-REMEDIATE[transcricao-formatacao-backfill]`
--    named (and any future malformed vision reply `parse_markup` had to keep
--    literal): a stored column an operator's list view can show, backfilled
--    here for the existing rows and written going forward by
--    `service.py::processar_extracao` via the seed's new `has_raw_markup`.
--    The contract generator's own gate (`contrato_gerador.derivacao`) checks
--    the ACTUAL quoted text at generation time regardless of this column —
--    this flag is for legibility on the history list, not the enforcement
--    path.
--
-- WHAT THIS DOES NOT DO
-- ---------------------
-- Does not touch the write-once trigger's existing three checks
-- (`texto_extraido` / `codigo` / `imovel_documento_id`) — it EXTENDS the same
-- function with two more frozen-once-set columns (`arquivo_origem_id`,
-- `substituida_por`), never weakens or bypasses what 111 already enforces.
-- Does not backfill the 5 existing unlinked rows with a retained source —
-- there is no source left to retain (the PDF was discarded at upload time,
-- before this migration existed). They stay `arquivo_origem_id IS NULL`, are
-- flagged `possui_marcacao_bruta` where that is literally true, and the
-- application refuses to offer "retranscrever" for a row with no source —
-- the honest answer for those 5 is still "reenvie o arquivo".
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. matricula_extracao_arquivos — the retained PDF for an unlinked upload
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.matricula_extracao_arquivos (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    storage_path   TEXT NOT NULL,
    nome_original  TEXT NOT NULL,
    mime_type      TEXT NOT NULL,
    tamanho_bytes  INTEGER NOT NULL,
    -- One value today (`DocumentoStore.tipos`, application-side allow-list —
    -- same shape `atendimento_contrato_versoes`' `TIPO_VERSAO` uses). A CHECK
    -- here too so a row cannot exist with anything else, independent of the
    -- application ever forgetting the allow-list.
    tipo_documento TEXT NOT NULL DEFAULT 'matricula'
        CHECK (tipo_documento = 'matricula'),
    enviado_por    UUID,
    deleted_at     TIMESTAMPTZ,
    delete_motivo  TEXT,
    -- Stamped from `documento_retencao.dias_para(..., 'imovel', 'matricula')`
    -- — the SAME platform policy row 111 already seeded for the linked PDF,
    -- reused rather than duplicated: both are "the matrícula PDF", differing
    -- only in which table currently holds it.
    retencao_ate   DATE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_matricula_extracao_arquivos_org
    ON social_wiring.matricula_extracao_arquivos (org_id, created_at DESC)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_sw_matricula_extracao_arquivos_retencao
    ON social_wiring.matricula_extracao_arquivos (retencao_ate)
    WHERE deleted_at IS NULL AND retencao_ate IS NOT NULL;

ALTER TABLE social_wiring.matricula_extracao_arquivos ENABLE ROW LEVEL SECURITY;

-- Every write to this table goes through the service-role
-- `get_matriculas_client` (mirrors the structured routes' RLS shape, 109) —
-- `authenticated` gets SELECT only, so a caller's own token can read but
-- never write, list, or soft-delete this table directly.
DROP POLICY IF EXISTS "matricula_extracao_arquivos_select_own_org"
    ON social_wiring.matricula_extracao_arquivos;
CREATE POLICY "matricula_extracao_arquivos_select_own_org"
    ON social_wiring.matricula_extracao_arquivos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "matricula_extracao_arquivos_service_role"
    ON social_wiring.matricula_extracao_arquivos;
CREATE POLICY "matricula_extracao_arquivos_service_role"
    ON social_wiring.matricula_extracao_arquivos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. matricula_extracoes -> the retained file, the supersede pointer, and
--    the raw-markup legibility flag
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.matricula_extracoes
    ADD COLUMN IF NOT EXISTS arquivo_origem_id     UUID,
    ADD COLUMN IF NOT EXISTS substituida_por        UUID,
    ADD COLUMN IF NOT EXISTS possui_marcacao_bruta  BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN social_wiring.matricula_extracoes.arquivo_origem_id IS
    'The matricula_extracao_arquivos row holding this UNLINKED extraction''s '
    'retained PDF. NULL for a linked extraction (see imovel_documento_id '
    'instead) or a legacy row uploaded before this migration, which kept no '
    'copy at all. See migration 135.';
COMMENT ON COLUMN social_wiring.matricula_extracoes.substituida_por IS
    'Set when a re-transcription of this row''s retained source creates a '
    'NEW row — same shape as negociacoes_venda.substituida_por (054): never '
    'rewritten in place, only marked. NULL = this is the live version. The '
    'superseded row is NEVER deleted while anything still cites it (109''s '
    'RESTRICT foreign keys) or superseded again once set. See migration 135.';
COMMENT ON COLUMN social_wiring.matricula_extracoes.possui_marcacao_bruta IS
    'True when texto_extraido still carries a literal **/<u>/</u> marker '
    '(noctusai_lib.integrations.documents.has_raw_markup) — either one of '
    'the pre-migration-113 rows NOC-REMEDIATE[transcricao-formatacao-backfill] '
    'named, or a future malformed vision reply parse_markup had to keep '
    'literal. Legibility only: the contract generator checks the actual '
    'quoted text at generation time independently of this column. See '
    'migration 135.';

ALTER TABLE social_wiring.matricula_extracoes
    DROP CONSTRAINT IF EXISTS matricula_extracoes_arquivo_origem_fk;
ALTER TABLE social_wiring.matricula_extracoes
    ADD CONSTRAINT matricula_extracoes_arquivo_origem_fk
    FOREIGN KEY (arquivo_origem_id)
    REFERENCES social_wiring.matricula_extracao_arquivos (id) ON DELETE SET NULL;

-- Self-referential, ON DELETE SET NULL: same reasoning migration 054 used for
-- negociacoes_venda — a superseded row losing its successor (an edge-case
-- hard delete) becomes independently visible again rather than vanish.
ALTER TABLE social_wiring.matricula_extracoes
    DROP CONSTRAINT IF EXISTS matricula_extracoes_substituida_por_fk;
ALTER TABLE social_wiring.matricula_extracoes
    ADD CONSTRAINT matricula_extracoes_substituida_por_fk
    FOREIGN KEY (substituida_por)
    REFERENCES social_wiring.matricula_extracoes (id) ON DELETE SET NULL;

-- A row can only ever hold ONE kind of retained source — never both a
-- linked imóvel document AND a standalone one.
ALTER TABLE social_wiring.matricula_extracoes
    DROP CONSTRAINT IF EXISTS matricula_extracoes_uma_fonte;
ALTER TABLE social_wiring.matricula_extracoes
    ADD CONSTRAINT matricula_extracoes_uma_fonte
    CHECK (imovel_documento_id IS NULL OR arquivo_origem_id IS NULL);

-- Only a CONCLUDED transcription can be superseded — the whole point of
-- "re-transcribe" is to replace text that already landed.
ALTER TABLE social_wiring.matricula_extracoes
    DROP CONSTRAINT IF EXISTS matricula_extracoes_substituida_exige_concluida;
ALTER TABLE social_wiring.matricula_extracoes
    ADD CONSTRAINT matricula_extracoes_substituida_exige_concluida
    CHECK (substituida_por IS NULL OR status = 'concluida');

-- "Which extraction is this document's LIVE transcription" — the read every
-- history-list / re-transcribe-eligibility check makes.
CREATE INDEX IF NOT EXISTS idx_sw_matricula_extracoes_substituida
    ON social_wiring.matricula_extracoes (substituida_por)
    WHERE substituida_por IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sw_matricula_extracoes_arquivo_origem
    ON social_wiring.matricula_extracoes (arquivo_origem_id)
    WHERE arquivo_origem_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. Extend the write-once guard (111) to the two new frozen-once-set columns
-- ----------------------------------------------------------------------------
-- Same function, same trigger — EXTENDED, not replaced. texto_extraido /
-- codigo / imovel_documento_id keep the exact behaviour 111 gave them.
CREATE OR REPLACE FUNCTION social_wiring.matricula_extracoes_protege_concluida()
  RETURNS trigger
  LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'concluida'
       AND NEW.texto_extraido IS DISTINCT FROM OLD.texto_extraido
       AND NEW.texto_extraido IS NOT NULL THEN
        RAISE EXCEPTION
            'matricula_extracoes %: texto_extraido não pode ser alterado '
            'após status = concluida', OLD.id;
    END IF;

    IF OLD.codigo IS NOT NULL
       AND NEW.codigo IS DISTINCT FROM OLD.codigo THEN
        RAISE EXCEPTION
            'matricula_extracoes %: codigo não pode ser alterado após '
            'vinculado a um imóvel', OLD.id;
    END IF;

    IF OLD.imovel_documento_id IS NOT NULL
       AND NEW.imovel_documento_id IS DISTINCT FROM OLD.imovel_documento_id THEN
        RAISE EXCEPTION
            'matricula_extracoes %: imovel_documento_id não pode ser '
            'alterado após vinculado', OLD.id;
    END IF;

    -- Migration 135: the standalone retained-file pointer is set once, at
    -- insert, exactly like imovel_documento_id above — never re-pointed at a
    -- different file.
    IF OLD.arquivo_origem_id IS NOT NULL
       AND NEW.arquivo_origem_id IS DISTINCT FROM OLD.arquivo_origem_id THEN
        RAISE EXCEPTION
            'matricula_extracoes %: arquivo_origem_id não pode ser alterado '
            'após vinculado', OLD.id;
    END IF;

    -- Migration 135: a row is superseded at most once. The one legitimate
    -- transition is NULL -> a new row's id; changing it again (re-pointing
    -- an already-superseded row at yet another successor) is refused rather
    -- than silently allowed.
    IF OLD.substituida_por IS NOT NULL
       AND NEW.substituida_por IS DISTINCT FROM OLD.substituida_por THEN
        RAISE EXCEPTION
            'matricula_extracoes %: substituida_por não pode ser alterado '
            'após definido', OLD.id;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION social_wiring.matricula_extracoes_protege_concluida() IS
    'Backstop for the write-once guarantee migration 109''s offsets rely on, '
    'extended by migration 135 to the retained-file pointer and the '
    'supersede pointer. Applies to EVERY role, including service_role.';

-- ----------------------------------------------------------------------------
-- 4. Backfill: flag the existing rows that already carry raw markup
-- ----------------------------------------------------------------------------
-- The 5 rows NOC-REMEDIATE[transcricao-formatacao-backfill] named (and any
-- other concluded row with the same defect) — a data-only UPDATE, not a
-- rewrite of texto_extraido, so the write-once trigger above has no opinion
-- on it (this column is not one of the four it guards, and even if it were,
-- possui_marcacao_bruta starts at its NOT NULL DEFAULT false on every row,
-- so this is the one write that ever sets it true).
UPDATE social_wiring.matricula_extracoes
SET possui_marcacao_bruta = true
WHERE status = 'concluida'
  AND texto_extraido IS NOT NULL
  AND (
      texto_extraido LIKE '%**%'
      OR texto_extraido ~* '<u>'
      OR texto_extraido ~* '</u>'
  );
