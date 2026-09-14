-- ============================================================================
-- Migration 113 · social_wiring: inline formatting (bold/underline) for the
-- matrícula and certidão transcripts, plus the certidão text layer itself
--
-- CONTEXT: `projects/abnt-formatting-CONTRACT.md`. The seed's transcription
-- ladder (S1) now returns bold/underline as `FormatRange`s alongside the
-- plain text it always returned; the seed's ABNT renderers (S2) turn a text
-- + its ranges into an ABNT-formatted PDF or a Word-pasteable HTML fragment.
-- This migration is where those two ranges land for THIS product's two
-- transcript surfaces.
--
-- 1. MATRÍCULA — formatacao RIDES ALONGSIDE THE EXISTING texto_extraido
-- --------------------------------------------------------------------------
-- `matricula_extracoes.texto_extraido` has existed since migration 092; this
-- adds its sibling column. `NOT NULL DEFAULT '[]'` (not nullable): every row
-- either has ranges or it has none, and "no ranges" and "column not filled
-- in yet" must never be the same NULL — `ranges_from_json` already treats a
-- genuinely-absent value (a row written before this migration) as `()`, but
-- that is a property of the READ side, not a reason to let a WRITE leave the
-- column NULL for a row created after this ships.
--
-- 🔴 5 rows in prod already hold `texto_extraido` with literal `**bold**` /
-- `<u>…</u>` markers baked into the PLAIN TEXT — the OLD vision prompt, before
-- the seed learned to parse markup into ranges instead of leaving it inline.
-- Migration 111's write-once trigger (`matricula_extracoes_protege_concluida`)
-- refuses to let `texto_extraido` be REWRITTEN once `status = 'concluida'`,
-- and this migration does not touch that trigger — so those five rows keep
-- their literal markers and get `formatacao = '[]'` (the column default)
-- until someone re-transcribes them. Named follow-up:
-- `NOC-REMEDIATE[transcricao-formatacao-backfill]`, tracked where the write
-- happens (`app/modules/matriculas/service.py::processar_extracao`).
--
-- 2. CERTIDÃO — texto_extraido DID NOT EXIST HERE AT ALL
-- --------------------------------------------------------------------------
-- Unlike matrículas, `certidao_resultados` never stored the PDF's own text —
-- `_extract_pdf_text` in `app/modules/certidoes/service.py` extracted it
-- on the fly, fed it to `_analyze_with_ai`, and threw it away. Slice S3
-- persists it for the first time, alongside its formatting, so the operator
-- can read (and export, ABNT-formatted) the certidão text the same way a
-- matrícula transcript already works. `tem_transcricao` is a GENERATED
-- column rather than a written flag: a written boolean can drift from the
-- text it describes (a bug that clears `texto_extraido` but forgets the
-- flag), a generated one cannot — it IS `texto_extraido IS NOT NULL`, always.
--
-- 🔴 THE POLLING SURFACE MUST NEVER CARRY THIS TEXT. `GET /consultas/{id}`
-- is read every few seconds while a consulta processes; `certidoes_por_parte`
-- backs a panel that lists many resultados at once. Both used to
-- `select("*")` — harmless before this migration, a CPF-bearing-text leak
-- to a polling response after it. `app/modules/certidoes/service.py` /
-- `routers/certidoes.py` switch those reads to an explicit column list that
-- EXCLUDES `texto_extraido` / `formatacao` and INCLUDES `tem_transcricao` —
-- see `RESULTADO_COLUNAS_SEM_TEXTO` in this migration's companion PR. The
-- full text is served ONLY by the two new `.../transcricao` routes, each
-- LGPD-logged like every other certidão content read.
--
-- No RLS change: both tables already scope reads to `org_id` (migrations 091
-- / 092) and the columns this file adds ride under that same policy.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. matricula_extracoes.formatacao
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.matricula_extracoes
    ADD COLUMN IF NOT EXISTS formatacao JSONB NOT NULL DEFAULT '[]';

COMMENT ON COLUMN social_wiring.matricula_extracoes.formatacao IS
    'FormatRange[] (noctusai_lib.integrations.documents.formatting.'
    'ranges_to_json) over texto_extraido — bold/underline offsets from the '
    'seed transcription ladder. "[]" for every row transcribed before this '
    'migration; see this file''s header for the 5-row backfill follow-up.';

-- ----------------------------------------------------------------------------
-- 2. certidao_resultados — the text layer this table never had, plus its
--    formatting and the generated "has one" flag
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS texto_extraido TEXT;

COMMENT ON COLUMN social_wiring.certidao_resultados.texto_extraido IS
    'The certidão PDF''s own text, read through the seed transcriber ('
    '_extract_pdf_text, text-layer only — same max_vision_pages=0 cost '
    'posture as the AI-analysis leg). NULL when nothing trustworthy was '
    'there or the transcription failed; a failure never fails the '
    'certidão itself. 🔴 NEVER select("*") this column into a polling '
    'response — see RESULTADO_COLUNAS_SEM_TEXTO in service.py.';

ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS formatacao JSONB NOT NULL DEFAULT '[]';

COMMENT ON COLUMN social_wiring.certidao_resultados.formatacao IS
    'FormatRange[] over texto_extraido, same shape and same "never poll '
    'this" rule as matricula_extracoes.formatacao above.';

ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS tem_transcricao BOOLEAN
        GENERATED ALWAYS AS (texto_extraido IS NOT NULL) STORED;

COMMENT ON COLUMN social_wiring.certidao_resultados.tem_transcricao IS
    'GENERATED, not written: always texto_extraido IS NOT NULL, so it can '
    'never drift from the column it describes. The frontend gates the '
    'transcript buttons ([Transcrição PDF] / [Copiar]) on this flag alone — '
    'it is safe to select in a polling response precisely because it never '
    'carries the text itself.';
