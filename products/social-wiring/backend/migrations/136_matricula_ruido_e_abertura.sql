-- ============================================================================
-- Migration 136 · social_wiring: page furniture is recorded as RANGES, and
-- the abertura is decomposed into typed blocks
--
-- CONTEXT
-- -------
-- A matrícula certidão is transcribed page by page and the pages are joined
-- into one `texto_extraido` (092/113). Every page carries furniture —
-- running headers, the registry's watermark, footers, "continua no verso",
-- an ONR validation URL, and on viewer exports a `SOLICITADO POR: <nome> -
-- CPF/CNPJ: …` requester stamp. The join puts all of it INSIDE the act spans
-- 109's segmenter produces, because that segmenter's contract is explicitly
-- "NOTHING IS DROPPED": spans are contiguous, each act runs to the next
-- header, the last runs to EOF.
--
-- That contract is correct and this migration does not touch it. But it
-- means the contract generator, which quotes an act VERBATIM into a deed,
-- would print a page header, a fee table, a validation URL — and a third
-- party's CPF — into a signed instrument. Verified live 2026-09-18 on both
-- clean extractions: one act carried ~1.7 KB of certification trailer, and
-- another carried a whole page break mid-sentence.
--
-- WHY RANGES AND NOT A CLEANED STRING
-- -----------------------------------
-- `texto_extraido` is the audit artifact. It is what a cartório compares
-- against its own book, it is write-once (111), and its retention is an LGPD
-- obligation (111/135). Rewriting it to drop furniture would break the
-- offsets every `matricula_atos` row, `matricula_ato_detalhes` hit and
-- contract selection already holds, and would destroy the very fidelity that
-- makes the quote defensible. So nothing is removed: the furniture is
-- RECORDED as offsets, exactly the way 113 recorded bold/underline, and the
-- QUOTE subtracts them at render time.
--
-- 🔴 WHY POSITION AND NOT REPETITION
-- ----------------------------------
-- The obvious detector — "a line that repeats is furniture" — is WRONG and
-- was disproven on real data before this was written: the officer's closing
-- signature (`Oficial, ____ <nome>`) repeats 3–5× in a single document and
-- is genuine registry content. What distinguishes furniture is its POSITION
-- at a page boundary. The detector therefore runs at transcription time,
-- against `TranscriptionResult.pages`, where page boundaries still exist —
-- they are lost the moment the pages are joined. Detection is deliberately
-- CONSERVATIVE: a span it is unsure about is not noise, because
-- over-stripping silently removes registry text from a deed while
-- under-stripping is visible and correctable.
--
-- WHAT THIS DOES
-- --------------
-- 1. `matricula_extracoes.ruido` — the detected furniture, as offsets into
--    this row's own `texto_extraido`. Same shape and same reasoning as 113's
--    `formatacao`: a JSONB array of `{start, end, kind}`. Frozen once the
--    row concludes, by the SAME guard 111 put on `texto_extraido`, because
--    the quote is a function of both and a deed already generated must keep
--    resolving to the text it actually quoted.
-- 2. `matricula_abertura_blocos` — the abertura's typed sub-spans
--    (`descricao_imovel`, `cadastro_municipal`, `proprietarios`,
--    `registro_anterior`). The contract's `objeto` clause needs the property
--    description SPECIFICALLY, not the whole abertura: a cleaned abertura
--    still ends in `PROPRIETÁRIOS: …`, which on a resold property names the
--    PREVIOUS owners, so quoting the block wholesale would name the wrong
--    parties in a deed. Offsets only, same discipline as `matricula_atos`.
--
-- WHAT THIS DOES NOT DO
-- ---------------------
-- Does not alter `matricula_atos` or its "contiguous, covers everything"
-- invariant — acts still span the whole text; only the QUOTE subtracts
-- noise. Does not weaken 111/135's write-once guard: it extends the same
-- function with one more frozen-once-concluded column. Does not backfill
-- `ruido` for existing rows — the page boundaries those rows were built from
-- were never persisted, so there is nothing to detect against. Existing rows
-- keep `ruido = '[]'` (their quotes behave exactly as before) and are
-- repaired the sanctioned way, by `criar_retranscricao` (135) re-running
-- from the retained source. A row with no retained source still answers
-- "reenvie o arquivo".
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. matricula_extracoes.ruido — page furniture as offsets
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.matricula_extracoes
    ADD COLUMN IF NOT EXISTS ruido JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN social_wiring.matricula_extracoes.ruido IS
    'Page furniture detected at transcription time, as offsets into THIS '
    'row''s texto_extraido: [{"start": int, "end": int, "kind": '
    '"cabecalho_pagina"|"rodape_pagina"}]. Same shape and reasoning as 113''s '
    'formatacao — texto_extraido is never rewritten, the QUOTE subtracts '
    'these spans at render time (estrutura_service._citacao). Empty array = '
    'nothing detected, or a row transcribed before migration 136, whose '
    'quote therefore behaves exactly as it did before. See migration 136.';

-- Shape guard. A malformed entry here would silently shift a legal quote, so
-- it is refused at write time rather than discovered in a generated deed.
-- A CHECK cannot contain a subquery, so the per-element walk lives in an
-- IMMUTABLE helper — the same shape `jsonb` validators elsewhere in this
-- schema use.
CREATE OR REPLACE FUNCTION social_wiring.matricula_ruido_valido(v JSONB)
  RETURNS BOOLEAN
  LANGUAGE sql
  IMMUTABLE
  PARALLEL SAFE
AS $$
    SELECT jsonb_typeof(v) = 'array'
       AND NOT EXISTS (
           SELECT 1
             FROM jsonb_array_elements(v) AS e
            WHERE jsonb_typeof(e) <> 'object'
               OR jsonb_typeof(e -> 'start') <> 'number'
               OR jsonb_typeof(e -> 'end') <> 'number'
               OR (e ->> 'start')::numeric < 0
               OR (e ->> 'end')::numeric < (e ->> 'start')::numeric
               OR COALESCE(e ->> 'kind', '') NOT IN
                  ('cabecalho_pagina', 'rodape_pagina')
       );
$$;

COMMENT ON FUNCTION social_wiring.matricula_ruido_valido(JSONB) IS
    'Shape validator for matricula_extracoes.ruido — an array of '
    '{start, end, kind} spans with start >= 0 and end >= start. See '
    'migration 136.';

ALTER TABLE social_wiring.matricula_extracoes
    DROP CONSTRAINT IF EXISTS matricula_extracoes_ruido_shape;
ALTER TABLE social_wiring.matricula_extracoes
    ADD CONSTRAINT matricula_extracoes_ruido_shape
    CHECK (social_wiring.matricula_ruido_valido(ruido));

-- ----------------------------------------------------------------------------
-- 2. matricula_abertura_blocos — the abertura's typed sub-spans
-- ----------------------------------------------------------------------------
-- CASCADE on the extraction, matching matricula_atos (109): these are
-- derived from the transcription and have no meaning without it. Unlike an
-- act, no contract selection points at a block — the `objeto` clause resolves
-- the description through the extraction, so there is nothing for a RESTRICT
-- to protect here.
CREATE TABLE IF NOT EXISTS social_wiring.matricula_abertura_blocos (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    extracao_id   UUID NOT NULL
        REFERENCES social_wiring.matricula_extracoes (id) ON DELETE CASCADE,

    campo         TEXT NOT NULL CHECK (campo IN (
                      'descricao_imovel',
                      'cadastro_municipal',
                      'proprietarios',
                      'registro_anterior'
                  )),

    -- Offsets into texto_extraido, never text — the same discipline
    -- matricula_atos holds, for the same reason: the contract quotes the
    -- slice literally, so storing a copy would let the two drift.
    char_inicio   INT NOT NULL CHECK (char_inicio >= 0),
    char_fim      INT NOT NULL,
    -- The recognised label token (`IMÓVEL:`) for UI highlighting. The block
    -- itself starts AFTER the label: the docx template already renders
    -- "IMÓVEL:" around the slot, so including it would double it.
    rotulo_inicio INT NOT NULL CHECK (rotulo_inicio >= 0),
    rotulo_fim    INT NOT NULL,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT matricula_abertura_blocos_span_valido
        CHECK (char_fim >= char_inicio),
    CONSTRAINT matricula_abertura_blocos_rotulo_valido
        CHECK (rotulo_fim >= rotulo_inicio AND rotulo_fim <= char_inicio)
);

-- One block per field per extraction: a second `IMÓVEL:` would make
-- "the property description" ambiguous, and an ambiguous legal quote is a
-- defect, not a choice to resolve at read time.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sw_matricula_abertura_blocos_campo
    ON social_wiring.matricula_abertura_blocos (extracao_id, campo);

CREATE INDEX IF NOT EXISTS idx_sw_matricula_abertura_blocos_org_extracao
    ON social_wiring.matricula_abertura_blocos (org_id, extracao_id);

ALTER TABLE social_wiring.matricula_abertura_blocos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "matricula_abertura_blocos_select_own_org"
    ON social_wiring.matricula_abertura_blocos;
CREATE POLICY "matricula_abertura_blocos_select_own_org"
    ON social_wiring.matricula_abertura_blocos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "matricula_abertura_blocos_service_role"
    ON social_wiring.matricula_abertura_blocos;
CREATE POLICY "matricula_abertura_blocos_service_role"
    ON social_wiring.matricula_abertura_blocos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. Extend the write-once guard (111/135) to `ruido`
-- ----------------------------------------------------------------------------
-- Same function, same trigger — EXTENDED, not replaced. The five checks
-- 111 and 135 established keep their exact behaviour.
--
-- `ruido` is frozen for the same reason `texto_extraido` is: the quote a
-- generated deed carries is a function of BOTH, so letting the noise ranges
-- move after the fact would silently change what an already-signed document
-- is understood to have quoted. Repair is a re-transcription (135), which
-- supersedes with a NEW row and leaves this one intact.
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

    IF OLD.arquivo_origem_id IS NOT NULL
       AND NEW.arquivo_origem_id IS DISTINCT FROM OLD.arquivo_origem_id THEN
        RAISE EXCEPTION
            'matricula_extracoes %: arquivo_origem_id não pode ser alterado '
            'após vinculado', OLD.id;
    END IF;

    IF OLD.substituida_por IS NOT NULL
       AND NEW.substituida_por IS DISTINCT FROM OLD.substituida_por THEN
        RAISE EXCEPTION
            'matricula_extracoes %: substituida_por não pode ser alterado '
            'após definido', OLD.id;
    END IF;

    -- Migration 136: the noise ranges the quote subtracts. Frozen once the
    -- transcription concludes, exactly like texto_extraido above — the two
    -- together define what a generated deed quoted.
    IF OLD.status = 'concluida'
       AND NEW.ruido IS DISTINCT FROM OLD.ruido THEN
        RAISE EXCEPTION
            'matricula_extracoes %: ruido não pode ser alterado após '
            'status = concluida', OLD.id;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION social_wiring.matricula_extracoes_protege_concluida() IS
    'Backstop for the write-once guarantee migration 109''s offsets rely on, '
    'extended by 135 to the retained-file and supersede pointers and by 136 '
    'to the noise ranges the quote subtracts. Applies to EVERY role, '
    'including service_role.';

NOTIFY pgrst, 'reload schema';
