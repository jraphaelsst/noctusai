-- ============================================================================
-- Migration 254 -- social_wiring: per-read outcomes of the routed document
-- extraction (the model-routing learning loop)
--
-- WHAT THIS IS
-- ------------
-- Owner direction, 2026-10-13: "use the comparison and disagreement data to
-- learn the models' performance/accuracy/precision and choose which models
-- are best for each data and document, and the second best as fallback; then
-- conciliation only on low-reliability extractions that don't pass the first
-- model's quality and trust gate."
--
-- The seed reads a document ONCE with the routed primary model
-- (`noctusai_lib.integrations.documents.roteamento`), judges every critical
-- field (`documents.confianca`) and reads once more with the fallback model
-- only for a doubtful one. Every such read lands here, ONE ROW PER CRITICAL
-- FIELD: the model(s), the gate verdict + reasons, whether the fallback ran,
-- whether the two reads agreed, what became of the field, and the read's
-- cost. When a human later settles the field -- accepting/rejecting the
-- agreement-gate review (`cliente_campo_conflitos`, origens
-- `extracao_leitura_a/b`) or typing a value over the machine one -- the row
-- gets the resolution and whether each read was right.
-- `noctus.dev.roteamento_modelos_recalibrar` turns resolved rows into
-- precision per (model, doc type, field) and regenerates the routing table.
--
-- 🔴 NO PII. Field NAMES, model ids, verdict codes and costs only. A reading
-- is represented by `impressao_*` -- a 24-bit fingerprint (6 hex chars of
-- SHA-256 over the field + normalised value, `documents.confianca.impressao`)
-- that tells two readings apart without being reversible to the value (~60
-- CPF candidates per fingerprint).
--
-- FORWARD-ONLY, IDEMPOTENT. RLS mirrors `cliente_campo_conflitos` (138) in the
-- org-picker-aware form 211 converted it to (`current_org_id_for('social_wiring')`):
-- own-org SELECT for authenticated, ALL for service_role.
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.extracao_leitura_resultados (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL,
    cliente_id           UUID
        REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    documento_id         UUID,
    tipo_documento       TEXT,

    -- Seed field name (`nome`, `cpf`, `rg`, `rne`, `estado_civil`, ...).
    campo                TEXT NOT NULL,

    modo                 TEXT NOT NULL
        CHECK (modo IN ('producao', 'medicao', 'leitura_unica')),
    modelo_primario      TEXT NOT NULL,
    modelo_fallback      TEXT,
    fallback_executado   BOOLEAN NOT NULL DEFAULT false,

    veredito             TEXT NOT NULL
        CHECK (veredito IN ('confiavel', 'duvidoso', 'ausente')),
    motivos              TEXT[] NOT NULL DEFAULT '{}',
    resultado            TEXT NOT NULL
        CHECK (resultado IN ('armazenado', 'concordou', 'divergiu', 'dv',
                             'sem_leitura', 'nao_conciliado')),
    acordo               BOOLEAN,
    impressao_primaria   TEXT,
    impressao_fallback   TEXT,

    -- The whole document read's spend (every transcription of it), repeated
    -- on each of its field rows so a row is self-contained.
    usd_documento        NUMERIC(12, 6) NOT NULL DEFAULT 0,
    tokens_entrada       INTEGER NOT NULL DEFAULT 0,
    tokens_saida         INTEGER NOT NULL DEFAULT 0,

    -- Filled when a human settles the field (see the header).
    resolucao            TEXT
        CHECK (resolucao IN ('conflito_aceito', 'conflito_rejeitado', 'edicao_manual',
                             'confirmado')),
    impressao_final      TEXT,
    primario_correto     BOOLEAN,
    fallback_correto     BOOLEAN,
    resolvido_em         TIMESTAMPTZ,

    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.extracao_leitura_resultados IS
    'One row per critical field of a routed document read (migration 254): '
    'model, trust-gate verdict, fallback, agreement, cost, and the later human '
    'resolution. Fingerprints only, never values. Feeds the model routing table.';

CREATE INDEX IF NOT EXISTS idx_sw_extracao_leitura_resultados_cliente_campo
    ON social_wiring.extracao_leitura_resultados (org_id, cliente_id, campo);

CREATE INDEX IF NOT EXISTS idx_sw_extracao_leitura_resultados_documento
    ON social_wiring.extracao_leitura_resultados (documento_id);

-- The recalibration export: resolved rows only.
CREATE INDEX IF NOT EXISTS idx_sw_extracao_leitura_resultados_resolvidos
    ON social_wiring.extracao_leitura_resultados (tipo_documento, campo)
    WHERE resolucao IS NOT NULL;

ALTER TABLE social_wiring.extracao_leitura_resultados ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "extracao_leitura_resultados_select_own_org"
    ON social_wiring.extracao_leitura_resultados;
CREATE POLICY "extracao_leitura_resultados_select_own_org"
    ON social_wiring.extracao_leitura_resultados
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "extracao_leitura_resultados_service_role"
    ON social_wiring.extracao_leitura_resultados;
CREATE POLICY "extracao_leitura_resultados_service_role"
    ON social_wiring.extracao_leitura_resultados
    FOR ALL TO service_role USING (true) WITH CHECK (true);
