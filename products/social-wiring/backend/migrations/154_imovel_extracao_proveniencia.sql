-- ============================================================================
-- Migration 154 · social_wiring: matrícula/IPTU/CND → imovel_dados under the
-- D1 write policy — provenance, conflicts, retry bookkeeping, and the ONE
-- sanctioned rewrite of a concluded transcription (legacy markup strip)
-- ============================================================================
-- Roadmap: project-history/roadmaps/sw-extraction-contract-gate-2026-09.md
-- (owner decisions D1 write policy, D3 retries ≤ 2; shared field-state
-- contract: a field is MACHINE-PENDING iff `<campo>_origem IS NOT NULL AND
-- <campo>_origem <> 'manual' AND <campo>_confirmado_em IS NULL`).
--
-- 1. imovel_dados — provenance quintets for the contract-feeding fields that
--    had none (`numero_registro_imoveis`, `prefeitura_cadastro_imobiliario`,
--    `situacao_onus`), and the missing `_origem` for the two confirmed-text
--    fields (`titulo_aquisitivo_texto`, `onus_credor`). `_documento_id` is a
--    POLYMORPHIC pointer (a `matricula_extracoes.id` or an
--    `imovel_documentos.id`) — deliberately not an FK, same reasoning 138
--    gave `cliente_campo_conflitos.fonte_id`.
--
--    BACKFILL: every value already present was written by a human (the PATCH
--    route / the confirm PUTs) EXCEPT a `prefeitura_cadastro_imobiliario` a
--    guia de IPTU read suggested (`documentos_service.extrair_estrutura`,
--    118) — that one is attributed back to its guia when the guia's own
--    `inscricao_imobiliaria` matches; everything else is stamped `'manual'`.
--    Stamping `'manual'` is the conservative direction: it never makes a
--    human value look machine-pending, and it protects it from overwrite.
--
-- 2. imovel_campo_conflitos — D1's "human value → conflict + notify, never
--    overwrite" (and machine-vs-machine disagreement) for `imovel_dados`.
--    Same shape and same one-open-per-field rule as `cliente_campo_conflitos`
--    (138). `valor_*` are JSONB because two conflict-able fields are GROUPS
--    (the título aquisitivo pointer, the ônus source acts).
--
-- 3. imovel_documentos — status/erro/tentativas for the 118 structured read,
--    which 118 deliberately left lifecycle-less. D3 changes that: a failed
--    read is retried by the imovel_hub sweep at most twice, then stays
--    `erro` for a human. NULL status = the read never applied (tipos without
--    one, or rows uploaded before this migration).
--
-- 4. matricula_extracoes — `erro_codigo` (the seed's machine error code, so
--    the sweep can tell a retryable failure — credit exhaustion, rate limit —
--    from a permanent one — an empty PDF) and `retentativas` (automatic
--    retries already spent; D3 caps it at 2).
--
-- 5. The write-once trigger (111/135/136) gains exactly ONE exception:
--    removing legacy `**` / `<u>` / `</u>` markers from a concluded
--    `texto_extraido` (and, in that same UPDATE, rewriting `ruido` to the
--    shifted offsets). Verified in the trigger, not trusted from the app:
--    the new text must equal the old one with markers removed, and be
--    strictly shorter. Every other rewrite is refused exactly as before.
--    Why: 5 of 8 prod rows carry literal markers (the contract BLOCKS on
--    them) and pre-135 rows keep no source PDF to re-transcribe from — the
--    markers ARE the formatting, so stripping them is lossless (see
--    `noctusai_lib.integrations.documents.matricula_marcacao`).
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. imovel_dados provenance
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_dados
    ADD COLUMN IF NOT EXISTS numero_registro_imoveis_origem                 TEXT,
    ADD COLUMN IF NOT EXISTS numero_registro_imoveis_documento_id           UUID,
    ADD COLUMN IF NOT EXISTS numero_registro_imoveis_em                     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS numero_registro_imoveis_confirmado_por         UUID,
    ADD COLUMN IF NOT EXISTS numero_registro_imoveis_confirmado_em          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS prefeitura_cadastro_imobiliario_origem         TEXT,
    ADD COLUMN IF NOT EXISTS prefeitura_cadastro_imobiliario_documento_id   UUID,
    ADD COLUMN IF NOT EXISTS prefeitura_cadastro_imobiliario_em             TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS prefeitura_cadastro_imobiliario_confirmado_por UUID,
    ADD COLUMN IF NOT EXISTS prefeitura_cadastro_imobiliario_confirmado_em  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS situacao_onus_origem                           TEXT,
    ADD COLUMN IF NOT EXISTS situacao_onus_documento_id                     UUID,
    ADD COLUMN IF NOT EXISTS situacao_onus_em                               TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS situacao_onus_confirmado_por                   UUID,
    ADD COLUMN IF NOT EXISTS situacao_onus_confirmado_em                    TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS titulo_aquisitivo_texto_origem                 TEXT,
    ADD COLUMN IF NOT EXISTS onus_credor_origem                             TEXT;

COMMENT ON COLUMN social_wiring.imovel_dados.numero_registro_imoveis_origem IS
    'manual | matricula (read off the certidão heading) — who wrote '
    'numero_registro_imoveis. Machine-pending iff origem <> manual AND '
    'confirmado_em IS NULL (migration 154).';
COMMENT ON COLUMN social_wiring.imovel_dados.prefeitura_cadastro_imobiliario_origem IS
    'manual | matricula (CADASTRO MUNICIPAL block) | guia_iptu | cnd_iptu '
    '(migration 154).';
COMMENT ON COLUMN social_wiring.imovel_dados.situacao_onus_origem IS
    'manual | matricula (derived from the acts: an unreleased hipoteca / '
    'alienação fiduciária / penhora / usufruto / indisponibilidade, else '
    'livre) (migration 154).';
COMMENT ON COLUMN social_wiring.imovel_dados.titulo_aquisitivo_texto_origem IS
    'manual | matricula (frase_titulo_aquisitivo over the título act''s '
    'instrumento). Confirmation stays titulo_aquisitivo_texto_confirmado_* '
    '(115) (migration 154).';
COMMENT ON COLUMN social_wiring.imovel_dados.onus_credor_origem IS
    'manual | matricula (credor of the ônus source acts). Confirmation stays '
    'onus_credor_confirmado_* (115) (migration 154).';

-- Backfill — see header §1. Guia-sourced inscrição first, then everything
-- else present and unattributed is the human's.
UPDATE social_wiring.imovel_dados d
SET prefeitura_cadastro_imobiliario_origem = doc.tipo_documento,
    prefeitura_cadastro_imobiliario_documento_id = doc.id,
    prefeitura_cadastro_imobiliario_em = COALESCE(d.updated_at, d.created_at)
FROM (
    SELECT DISTINCT ON (org_id, codigo, inscricao_imobiliaria)
           id, org_id, codigo, inscricao_imobiliaria, tipo_documento
      FROM social_wiring.imovel_documentos
     WHERE tipo_documento = 'guia_iptu'
       AND origem = 'ia'
       AND inscricao_imobiliaria IS NOT NULL
       AND deleted_at IS NULL
     ORDER BY org_id, codigo, inscricao_imobiliaria, created_at
) doc
WHERE d.org_id = doc.org_id
  AND d.codigo = doc.codigo
  AND d.prefeitura_cadastro_imobiliario = doc.inscricao_imobiliaria
  AND d.prefeitura_cadastro_imobiliario_origem IS NULL;

UPDATE social_wiring.imovel_dados
SET numero_registro_imoveis_origem = 'manual'
WHERE numero_registro_imoveis IS NOT NULL AND numero_registro_imoveis_origem IS NULL;

UPDATE social_wiring.imovel_dados
SET prefeitura_cadastro_imobiliario_origem = 'manual'
WHERE prefeitura_cadastro_imobiliario IS NOT NULL
  AND prefeitura_cadastro_imobiliario_origem IS NULL;

UPDATE social_wiring.imovel_dados
SET situacao_onus_origem = 'manual',
    situacao_onus_confirmado_por = onus_registrado_por,
    situacao_onus_confirmado_em = onus_registrado_em
WHERE situacao_onus IS NOT NULL AND situacao_onus_origem IS NULL;

UPDATE social_wiring.imovel_dados
SET titulo_aquisitivo_texto_origem = 'manual'
WHERE titulo_aquisitivo_texto IS NOT NULL AND titulo_aquisitivo_texto_origem IS NULL;

UPDATE social_wiring.imovel_dados
SET onus_credor_origem = 'manual'
WHERE onus_credor IS NOT NULL AND onus_credor_origem IS NULL;

-- ----------------------------------------------------------------------------
-- 2. imovel_campo_conflitos
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.imovel_campo_conflitos (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    codigo              TEXT NOT NULL,

    -- The imovel_dados field (or field GROUP: 'titulo_aquisitivo',
    -- 'onus_fonte') in conflict.
    campo               TEXT NOT NULL,

    -- PERMANENT snapshot of what was on imovel_dados at detection — the way
    -- back an accepted conflict needs (same contract as 138).
    valor_anterior      JSONB,
    origem_anterior     TEXT,

    valor_proposto      JSONB NOT NULL,
    origem_proposto     TEXT NOT NULL,
    documento_id_proposto UUID,
    confianca_proposta  TEXT,

    -- Polymorphic source pointer ('matricula_extracoes' | 'imovel_documentos').
    fonte_tabela        TEXT,
    fonte_id            UUID,

    status              TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'aceito', 'rejeitado')),
    notificado_em       TIMESTAMPTZ,
    decidido_por        UUID,
    decidido_em         TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_imovel_campo_conflitos_imovel
        FOREIGN KEY (org_id, codigo)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical)
        ON DELETE CASCADE
);

COMMENT ON TABLE social_wiring.imovel_campo_conflitos IS
    'One row per imovel_dados field where a machine reading (matrícula / '
    'guia de IPTU / CND) disagreed with a value already there (migration '
    '154, owner decision D1). Never auto-resolved: a human accepts (the '
    'proposed value lands, confirmed by the decider) or rejects (imovel_dados '
    'untouched). valor_anterior is never updated after insert.';

CREATE INDEX IF NOT EXISTS idx_sw_imovel_campo_conflitos_imovel
    ON social_wiring.imovel_campo_conflitos (org_id, codigo);

CREATE INDEX IF NOT EXISTS idx_sw_imovel_campo_conflitos_pendentes
    ON social_wiring.imovel_campo_conflitos (org_id, created_at DESC)
    WHERE status = 'pendente';

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_imovel_campo_conflitos_aberto
    ON social_wiring.imovel_campo_conflitos (org_id, codigo, campo)
    WHERE status = 'pendente';

ALTER TABLE social_wiring.imovel_campo_conflitos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imovel_campo_conflitos_select_own_org"
    ON social_wiring.imovel_campo_conflitos;
CREATE POLICY "imovel_campo_conflitos_select_own_org"
    ON social_wiring.imovel_campo_conflitos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "imovel_campo_conflitos_service_role"
    ON social_wiring.imovel_campo_conflitos;
CREATE POLICY "imovel_campo_conflitos_service_role"
    ON social_wiring.imovel_campo_conflitos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. imovel_documentos — structured-read lifecycle (D3)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_documentos
    ADD COLUMN IF NOT EXISTS estrutura_status      TEXT,
    ADD COLUMN IF NOT EXISTS estrutura_erro        TEXT,
    ADD COLUMN IF NOT EXISTS estrutura_tentativas  INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS estrutura_em          TIMESTAMPTZ;

ALTER TABLE social_wiring.imovel_documentos
    DROP CONSTRAINT IF EXISTS imovel_documentos_estrutura_status_check;
ALTER TABLE social_wiring.imovel_documentos
    ADD CONSTRAINT imovel_documentos_estrutura_status_check
    CHECK (estrutura_status IS NULL OR estrutura_status IN (
        'pendente', 'processando', 'ok', 'sem_dados', 'erro', 'ignorado'
    ));

COMMENT ON COLUMN social_wiring.imovel_documentos.estrutura_status IS
    'Lifecycle of the 118 structured read (numero/emitida_em/validade_ate/'
    'resultado/inscricao_imobiliaria). pendente is stamped at upload; erro '
    'is retried by the imovel_hub sweep at most twice (estrutura_tentativas '
    '<= 3), then left for a human (D3, migration 154). NULL = not applicable '
    'or pre-154.';

CREATE INDEX IF NOT EXISTS idx_sw_imovel_documentos_estrutura_pendente
    ON social_wiring.imovel_documentos (estrutura_status, estrutura_em)
    WHERE estrutura_status IN ('pendente', 'processando', 'erro')
      AND deleted_at IS NULL;

-- ----------------------------------------------------------------------------
-- 4. matricula_extracoes — retry bookkeeping (D3)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.matricula_extracoes
    ADD COLUMN IF NOT EXISTS erro_codigo   TEXT,
    ADD COLUMN IF NOT EXISTS retentativas  INT NOT NULL DEFAULT 0;

COMMENT ON COLUMN social_wiring.matricula_extracoes.erro_codigo IS
    'The seed transcriber''s machine error code on status=erro (e.g. '
    'insufficient_quota, rate_limited, empty_document). NULL on a pre-154 '
    'erro row = unknown, treated as retryable (migration 154).';
COMMENT ON COLUMN social_wiring.matricula_extracoes.retentativas IS
    'Automatic retries already spent by the matriculas sweep. D3: at most 2, '
    'then the row stays erro for a human (migration 154).';

-- ----------------------------------------------------------------------------
-- 5. Write-once trigger — the markup-strip exception
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
BEGIN
    IF OLD.status = 'concluida'
       AND NEW.texto_extraido IS DISTINCT FROM OLD.texto_extraido
       AND NEW.texto_extraido IS NOT NULL
       AND NOT v_strip THEN
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
    -- the same UPDATE, when (and only when) 154's markup strip rewrites it.
    IF OLD.status = 'concluida'
       AND NEW.ruido IS DISTINCT FROM OLD.ruido
       AND NOT v_strip THEN
        RAISE EXCEPTION
            'matricula_extracoes %: ruido não pode ser alterado após '
            'status = concluida', OLD.id;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION social_wiring.matricula_extracoes_protege_concluida() IS
    'Backstop for the write-once guarantee migration 109''s offsets rely on, '
    'extended by 135 (retained-file + supersede pointers), 136 (noise ranges) '
    'and 154 (the one sanctioned rewrite: stripping legacy **/<u> markers, '
    'verified here — the new text must equal the old minus marker tokens). '
    'Applies to EVERY role, including service_role.';

NOTIFY pgrst, 'reload schema';
