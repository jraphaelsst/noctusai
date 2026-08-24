-- ============================================================================
-- Migration 071 -- social_wiring: the name on the document, kept BESIDE the
--                  name from the registration
--
-- THE DECISION THIS ENCODES
-- -------------------------
-- A lead's name arrives from a registration: a lead form, Meta, OLX, Vista, an
-- XLSX import, or an operator typing it. That name is what the business already
-- knows the person as. The name printed on their RG or CPF is the legal one.
--
-- These are TWO FACTS, not two guesses at one fact, so they get two columns.
-- An earlier draft of this migration had the document overwrite
-- `nome_completo` and kept the displaced value in a `_anterior` column; that
-- was rejected, and the reason is worth recording: overwriting throws away the
-- very comparison that makes this feature valuable. Keeping both means the
-- question "how accurate is our registration data against official documents?"
-- is answerable across the whole base with one query, at any time, rather than
-- being destroyed one row at a time as documents arrive.
--
-- WHAT THIS DOES NOT DO
-- ---------------------
-- `nome_completo` is never written by extraction. Not overwritten, not
-- backfilled, not "filled in when empty". It belongs to the registration and
-- stays that way, so the two columns remain independently sourced and the
-- comparison stays meaningful.
--
-- The `nome_completo` checklist item likewise still derives from
-- `nome_completo` alone. Whether we hold the official document is already
-- answered by the `rg` / `cpf` checklist items; a second name item would ask
-- the same question twice.
--
-- WHEN A SECOND DOCUMENT DISAGREES
-- --------------------------------
-- The most recent high-confidence read wins `nome_oficial`. Nothing is lost:
-- every document keeps its own `extracao_nome`, so the full set of readings
-- stays on the documents and only the current best answer is denormalised onto
-- the client.
-- ============================================================================

-- 1 ── The official name + its provenance -----------------------------------

ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS nome_oficial                 TEXT,
    ADD COLUMN IF NOT EXISTS nome_oficial_origem          TEXT,
    ADD COLUMN IF NOT EXISTS nome_oficial_documento_id    UUID
        REFERENCES social_wiring.cliente_documentos(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS nome_oficial_em              TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS nome_oficial_confirmado_por  UUID,
    ADD COLUMN IF NOT EXISTS nome_oficial_confirmado_em   TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.clientes.nome_oficial IS
    'Full name as printed on an identity document, read by '
    'noctusai_lib.integrations.documents. NEVER written by hand or by an '
    'import — compare it against nome_completo, do not reconcile them.';

COMMENT ON COLUMN social_wiring.clientes.nome_completo IS
    'Name as supplied at registration (lead form, Meta, OLX, Vista, import, or '
    'typed). Extraction never touches this column; the document''s reading '
    'lives in nome_oficial so the two stay comparable.';

COMMENT ON COLUMN social_wiring.clientes.nome_oficial_origem IS
    'tipo_documento the name was read off: ''rg'', ''cpf'', ''cnh''.';

COMMENT ON COLUMN social_wiring.clientes.nome_oficial_confirmado_por IS
    'Set when a human vouched for a low-confidence read. NULL alongside a set '
    'nome_oficial means the machine wrote it unattended at high confidence.';

-- 2 ── What the extractor read, kept on the document ------------------------

ALTER TABLE social_wiring.cliente_documentos
    ADD COLUMN IF NOT EXISTS extracao_nome           TEXT,
    ADD COLUMN IF NOT EXISTS extracao_nome_confianca TEXT,
    ADD COLUMN IF NOT EXISTS extracao_nome_rotulo    TEXT;

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_confianca IS
    'Confidence of the DATA DE NASCIMENTO read (migration 068, when it was the '
    'only extracted field). The name has its own extracao_nome_confianca.';

COMMENT ON COLUMN social_wiring.cliente_documentos.extracao_rotulo IS
    'Label the DATA DE NASCIMENTO was found next to. See extracao_nome_rotulo '
    'for the name.';

-- 3 ── Suggestion lookup ----------------------------------------------------
--
-- Mirrors idx_sw_cliente_documentos_sugestao_pendente from 069. A separate
-- partial index rather than a widened one: the two fields are resolved
-- independently, so a document whose birthdate was already confirmed must
-- still be reachable as a pending NAME suggestion.

CREATE INDEX IF NOT EXISTS idx_sw_cliente_documentos_sugestao_nome_pendente
    ON social_wiring.cliente_documentos (cliente_id, extracao_em DESC)
    WHERE deleted_at IS NULL
      AND extracao_descartada_em IS NULL
      AND extracao_nome IS NOT NULL;

-- 4 ── The comparison, as a first-class surface -----------------------------
--
-- The whole point of holding both names is measuring one against the other, so
-- the normalisation that makes them comparable ships here rather than being
-- re-invented in each ad-hoc query. Accents, case, punctuation and repeated
-- spaces are noise; anything else is a real difference.
--
-- `translate()` rather than the `unaccent` extension: unaccent's function is
-- not marked IMMUTABLE, which blocks it from ever being used in an index or a
-- generated column, and this expression must stay usable in both.
--
-- security_invoker so the caller's RLS on `clientes` applies. A view without
-- it runs as its owner and would hand every org's names to any authenticated
-- reader.

CREATE OR REPLACE FUNCTION social_wiring.normalizar_nome(txt TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT NULLIF(
        regexp_replace(
            regexp_replace(
                translate(
                    upper(COALESCE(txt, '')),
                    'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑ',
                    'AAAAAEEEEIIIIOOOOOUUUUCN'
                ),
                '[^A-Z ]', ' ', 'g'
            ),
            ' +', ' ', 'g'
        ),
        ''
    );
$$;

COMMENT ON FUNCTION social_wiring.normalizar_nome(TEXT) IS
    'Comparison form of a person name: accents folded, non-letters dropped, '
    'whitespace collapsed, trimmed to NULL when empty. IMMUTABLE so it can be '
    'indexed.';

CREATE OR REPLACE VIEW social_wiring.vw_nome_conferencia
WITH (security_invoker = true)
AS
SELECT
    c.id                AS cliente_id,
    c.org_id,
    -- The registration name is whichever of the two the registration
    -- actually supplied. `nome` is the column every intake path has always
    -- written (10.150 of 10.255 rows at the time of this migration);
    -- `nome_completo` arrived with 068 and is populated only when an
    -- operator fills the checklist field, so it is preferred when present
    -- and `nome` is the fallback rather than the other way round.
    COALESCE(NULLIF(btrim(c.nome_completo), ''), NULLIF(btrim(c.nome), ''))
                        AS nome_registro,
    c.nome_oficial,
    c.nome_oficial_origem,
    c.nome_oficial_em,
    CASE
        WHEN c.nome_oficial IS NULL THEN 'sem_documento'
        WHEN COALESCE(NULLIF(btrim(c.nome_completo), ''), NULLIF(btrim(c.nome), '')) IS NULL
            THEN 'sem_registro'
        WHEN btrim(social_wiring.normalizar_nome(
                COALESCE(NULLIF(btrim(c.nome_completo), ''), c.nome)))
             IS NOT DISTINCT FROM
             btrim(social_wiring.normalizar_nome(c.nome_oficial))
            THEN 'confere'
        ELSE 'diverge'
    END                 AS situacao
FROM social_wiring.clientes c;

COMMENT ON VIEW social_wiring.vw_nome_conferencia IS
    'Registration name vs official-document name, per client. situacao: '
    'confere | diverge | sem_documento | sem_registro. This is the surface for '
    'measuring how accurate registration data is against official documents.';
