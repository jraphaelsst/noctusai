-- ============================================================================
-- Migration 165 · social_wiring: the write-once trigger (111/135/136/154)
-- gains a SECOND sanctioned rewrite — whole-line boilerplate deletion
-- ============================================================================
-- Roadmap: project-history/roadmaps/sw-extraction-contract-gate-2026-09.md
--
-- WHAT BROKE (verified live in prod, 2026-09-23)
-- -----------------------------------------------
-- `backfill_service.normalizar_extracao` (154) composes TWO removal passes
-- against a concluded `texto_extraido`: `remover_marcacao` (154's own
-- exception, the `**`/`<u>` strip) THEN `remover_boilerplate` — a second,
-- independent pass that deletes whole registry provenance/validation-stamp
-- LINES (`matricula_marcacao.remover_boilerplate`, backed by
-- `media.pdf_text.boilerplate_line_spans`). 154's trigger has exactly ONE
-- exception (`v_strip`, the markup strip) and refuses the second pass for
-- EVERY concluded row that carries one — 7 of the 8 real rows, including
-- EUROVILLE-535's matrícula, whose `texto_extraido` opens with "Valide
-- aqui\neste documento" ahead of "Mat. 3917 — Página 1/3 — PROT. 89.029".
--
-- THE NEW EXCEPTION — `v_strip_boilerplate`
-- -------------------------------------------
-- Verified in the trigger, never trusted from the app, mirroring `v_strip`'s
-- own discipline:
--   1. `OLD.status = 'concluida'`, both texts present, `NEW` strictly
--      shorter than `OLD`, and the two are distinct.
--   2. `NEW` is `OLD` with WHOLE LINES deleted: splitting both on `E'\n'`,
--      `NEW`'s lines are an in-order SUBSEQUENCE of `OLD`'s lines — every
--      kept line survives byte-identical, in the same order; nothing is
--      inserted, reordered, or edited in place
--      (`social_wiring.matricula_texto_e_remocao_boilerplate`).
--   3. Every DELETED line is either blank, or matches the SAME boilerplate
--      pattern set `pdf_text._PROVENANCE_STAMP_PATTERNS` uses at fresh-
--      extraction time (`social_wiring.matricula_boilerplate_patterns`,
--      `social_wiring.matricula_linha_e_boilerplate`) — line-folded
--      (accent-stripped, case-folded via `translate()`/`lower()`, the same
--      `translate()`-not-`unaccent()` reasoning migration 071's
--      `normalizar_nome` gives) so a stamp that lost its accents in
--      transcription still matches.
--
-- This is exactly the shape `_aplicar_remocao` writes: `texto_extraido` +
-- `ruido` (offsets remapped through the SAME removal) in ONE UPDATE — so
-- `ruido` gets the identical `NOT v_strip AND NOT v_strip_boilerplate`
-- exception `v_strip` already has, never a separate one.
--
-- Every OTHER rewrite (an edited line, an inserted line, a reordered line,
-- or a deleted line that is neither blank nor a boilerplate match) is
-- refused exactly as before — `v_strip` and `v_strip_boilerplate` compose
-- with OR, neither weakens the other.
--
-- FORWARD-ONLY, IDEMPOTENT (`CREATE OR REPLACE FUNCTION` only; every branch
-- of 111/135/136/154 survives byte-for-byte).
-- 🔴 MIGRATION FILE ONLY — applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. The boilerplate pattern set — ONE list, mirrored from the seed's
--    `noctusai_lib.integrations.media.pdf_text._PROVENANCE_STAMP_PATTERNS`.
--    `backend/tests/test_migration_165_matricula_boilerplate_guard.py (TestBoilerplatePatternParity)`
--    asserts the two lists never drift apart. `\b` (Python) -> `\y`
--    (Postgres ARE word boundary — `\b` in Postgres regex means backspace,
--    NOT a boundary) is the only translation; every other token
--    (`\s`, `\S`, `\w`, `\W`) is identical in both engines.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.matricula_boilerplate_patterns()
RETURNS TEXT[]
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT ARRAY[
        '^valide\s+est[ea]\s+documento\y.*$',
        '^valide\s+aqui\s+est[ea]\s+documento\y.*$',
        '^valide\s+aqui$',
        '^este\s+documento$',
        '^solicitado\s+por\s*:.*$',
        '^documento\s+gerado\s+oficialmente\s+pelo\y.*$',
        '^registro\s+de\s+im[o0]veis\s+via\s+www\.[^\s]+$',
        '^todos\s+os\s+registros\s+de\s+im[o0]veis$',
        '^do\s+brasil\s+em\s+um\s+s[o0]\s+lugar$',
        '^https?://(assinador-web|[\w.-]*\.)?onr\.org\.br/\S*$',
        '^https?://selodigital\.tjsp\.jus\.br/?\S*$',
        '^www\.ridigital\.org\.br$',
        '^qr-?code$',
        '^documento\s+assinado\s+com\s+certificado\s+digital\y.*$',
        '^com\s+a\s+medida\s+provisoria\s+n[ºo°]?\s*2200-2/2001\y.*$',
        '^ser\s+confirmada\s+por\s+meio\s+do\s+programa\s+assinador\s+serpro\y.*$',
        '^as\s+orientacoes\s+para\s+instalar\s+o\s+assinador\s+serpro\y.*$',
        '^validacao\s+do\s+documento\s+digital\s+estao\s+disponiveis\s+em:?$',
        '^https?://(www\.)?serpro\.gov\.br/\S*$',
        '^republica\s+federativa\s+do\s+brasil$',
        '^ministerio\s+dos\s+transportes$',
        '^secretaria\s+nacional\s+de\s+transito\s*-?\s*senatran$',
        '^para\s+verificar\s+a\s+autenticidade\s+do\s+documento\s+acesse\s+o\s+site\s*:?$',
        '^selo\s*:\s*\S+$',
        '^ri\s*digital(\.onr)?(\s*\|.*)?$',
        '^registro\s+de\s+im[o0]veis\s*-\s*www\.[^\s]+$',
        '^\W*onr(\s+operador\s+nacional)?$',
        '^operador\s+nacional$',
        '^do\s+sistema\s+de\s+registro$',
        '^eletr[o0]nico\s+de\s+im[o0]veis$',
        '^`{3,}$'
    ]::TEXT[];
$$;

COMMENT ON FUNCTION social_wiring.matricula_boilerplate_patterns() IS
    'Registry provenance/validation-stamp line patterns, mirrored VERBATIM '
    'from noctusai_lib.integrations.media.pdf_text._PROVENANCE_STAMP_PATTERNS '
    '(Python \b -> Postgres \y, the ARE word-boundary escape; every other '
    'token unchanged). Parity asserted by '
    'backend/tests/test_migration_165_matricula_boilerplate_guard.py (TestBoilerplatePatternParity) — a '
    'change to either list without the other fails that test.';

-- ----------------------------------------------------------------------------
-- 2. One line, deletable or not — blank, or a boilerplate match once folded
--    (accents stripped via translate(), same reasoning migration 071's
--    normalizar_nome gives for not using the non-IMMUTABLE unaccent()
--    extension; case-folded via lower()).
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.matricula_linha_e_boilerplate(linha TEXT)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT
        btrim(COALESCE(linha, '')) = ''
        OR EXISTS (
            SELECT 1
            FROM unnest(social_wiring.matricula_boilerplate_patterns()) AS p(padrao)
            WHERE lower(
                    translate(
                        btrim(linha),
                        'áàâãäÁÀÂÃÄéèêëÉÈÊËíìîïÍÌÎÏóòôõöÓÒÔÕÖúùûüÚÙÛÜçÇñÑ',
                        'aaaaaAAAAAeeeeEEEEiiiiIIIIoooooOOOOOuuuuUUUUcCnN'
                    )
                  ) ~ p.padrao
        );
$$;

COMMENT ON FUNCTION social_wiring.matricula_linha_e_boilerplate(TEXT) IS
    'A single line (already split on E''\n'', not yet trimmed) is deletable '
    'under the migration 165 boilerplate exception iff it is blank OR its '
    'accent-folded, case-folded form matches one of '
    'matricula_boilerplate_patterns(). Blank lines are always deletable — '
    'remover_boilerplate never removes one AS boilerplate (it has nothing to '
    'match), but the guard is intentionally the more permissive superset so '
    'it also covers the outer leading/trailing blank-run trim '
    'clean_extraction_output performs at fresh-extraction time.';

-- ----------------------------------------------------------------------------
-- 3. Is `texto_novo` obtainable from `texto_antigo` by deleting ONLY
--    deletable whole lines, in place, preserving every other line
--    byte-for-byte and in order? A greedy left-to-right subsequence match:
--    a line that equals the next expected NEW line is kept; any other line
--    must be deletable or the whole rewrite is rejected. Greedy-earliest is
--    the standard, provably-correct algorithm for "is B a subsequence of
--    A" — it never rejects a valid alignment, because deletability here is
--    a property of a line's CONTENT alone, not its position, so which
--    occurrence of a repeated value gets matched cannot change the verdict.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.matricula_texto_e_remocao_boilerplate(
    texto_antigo TEXT,
    texto_novo   TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    linhas_antigas TEXT[];
    linhas_novas   TEXT[];
    n_antigas      INT;
    n_novas        INT;
    i              INT := 1;
    j              INT := 1;
BEGIN
    IF texto_antigo IS NULL OR texto_novo IS NULL THEN
        RETURN false;
    END IF;

    linhas_antigas := string_to_array(texto_antigo, E'\n');
    linhas_novas   := string_to_array(texto_novo, E'\n');
    n_antigas := COALESCE(array_length(linhas_antigas, 1), 0);
    n_novas   := COALESCE(array_length(linhas_novas, 1), 0);

    WHILE i <= n_antigas LOOP
        IF j <= n_novas AND linhas_antigas[i] = linhas_novas[j] THEN
            i := i + 1;
            j := j + 1;
        ELSIF social_wiring.matricula_linha_e_boilerplate(linhas_antigas[i]) THEN
            i := i + 1;
        ELSE
            RETURN false;
        END IF;
    END LOOP;

    -- Every OLD line has been accounted for (matched or deleted). NEW is a
    -- valid boilerplate-only deletion iff every NEW line was matched too —
    -- if lines remain in linhas_novas, NEW introduced content OLD never
    -- had, which is never a pure deletion.
    RETURN j > n_novas;
END;
$$;

COMMENT ON FUNCTION social_wiring.matricula_texto_e_remocao_boilerplate(TEXT, TEXT) IS
    'true iff texto_novo is texto_antigo with zero or more whole, deletable '
    '(matricula_linha_e_boilerplate) lines removed, every remaining line '
    'kept byte-identical and in order. The SQL half of the migration 165 '
    'exception — verified here, never trusted from the app. Mirrors the '
    'offset-tracking guarantee '
    'noctusai_lib.integrations.documents.matricula_marcacao.remover_boilerplate '
    'already enforces in Python (its own reconstruction check); this is the '
    'independent, server-side re-verification of the SAME claim.';

-- ----------------------------------------------------------------------------
-- 4. The write-once trigger (111/135/136/154) — `v_strip` untouched,
--    verbatim; every other branch untouched, verbatim; ONE new DECLARE and
--    the two conditions it composes into (texto_extraido, ruido) with OR.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION social_wiring.matricula_extracoes_protege_concluida()
  RETURNS trigger
  LANGUAGE plpgsql
AS $$
DECLARE
    -- Migration 154: the ONE sanctioned rewrite of a concluded text —
    -- removing legacy `**` / `<u>` / `</u>` markers. True only when the new
    -- text IS the old one minus marker tokens (same text once both are
    -- stripped) and strictly shorter.
    v_strip BOOLEAN :=
        OLD.status = 'concluida'
        AND OLD.texto_extraido IS NOT NULL
        AND NEW.texto_extraido IS NOT NULL
        AND NEW.texto_extraido IS DISTINCT FROM OLD.texto_extraido
        AND length(NEW.texto_extraido) < length(OLD.texto_extraido)
        AND regexp_replace(NEW.texto_extraido, '\*\*|</?[uU]>', '', 'g')
          = regexp_replace(OLD.texto_extraido, '\*\*|</?[uU]>', '', 'g');
    -- Migration 165: the SECOND sanctioned rewrite — deleting whole
    -- registry provenance/validation-stamp LINES (never editing, inserting,
    -- or reordering one). Verified by
    -- matricula_texto_e_remocao_boilerplate, not trusted from the app.
    v_strip_boilerplate BOOLEAN :=
        OLD.status = 'concluida'
        AND OLD.texto_extraido IS NOT NULL
        AND NEW.texto_extraido IS NOT NULL
        AND NEW.texto_extraido IS DISTINCT FROM OLD.texto_extraido
        AND length(NEW.texto_extraido) < length(OLD.texto_extraido)
        AND social_wiring.matricula_texto_e_remocao_boilerplate(
                OLD.texto_extraido, NEW.texto_extraido
            );
BEGIN
    IF OLD.status = 'concluida'
       AND NEW.texto_extraido IS DISTINCT FROM OLD.texto_extraido
       AND NEW.texto_extraido IS NOT NULL
       AND NOT v_strip
       AND NOT v_strip_boilerplate THEN
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

    -- 136: the noise ranges are frozen with the text — and move WITH it, in
    -- the same UPDATE, when (and only when) 154's markup strip or 165's
    -- boilerplate-line strip rewrites it.
    IF OLD.status = 'concluida'
       AND NEW.ruido IS DISTINCT FROM OLD.ruido
       AND NOT v_strip
       AND NOT v_strip_boilerplate THEN
        RAISE EXCEPTION
            'matricula_extracoes %: ruido não pode ser alterado após '
            'status = concluida', OLD.id;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION social_wiring.matricula_extracoes_protege_concluida() IS
    'Backstop for the write-once guarantee migration 109''s offsets rely on, '
    'extended by 135 (retained-file + supersede pointers), 136 (noise ranges), '
    '154 (sanctioned rewrite #1: stripping legacy **/<u> markers) and 165 '
    '(sanctioned rewrite #2: deleting whole registry-boilerplate lines) — '
    'both verified here, never trusted from the app. '
    'Applies to EVERY role, including service_role.';

NOTIFY pgrst, 'reload schema';
