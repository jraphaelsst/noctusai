-- ============================================================================
-- 186 — InfoSimples emission WATCHER + Receita PCEN acknowledgment
-- ============================================================================
-- (1) certidao_emissao_observacoes: ONE row per InfoSimples call, every tipo,
--     success or failure. Written best-effort by `certidoes/aprendizado.py`
--     (a recording failure is logged, never breaks the emission). LGPD: NO
--     token, birthdate, name or full CPF/CNPJ — `params` is an allowlist and
--     the document is an org-scoped HMAC key (`documento_hash`).
--     `fallback_de` links a `2via` retry (or a `nova` after a failed `2via`) to
--     the call that triggered it; `assinatura` is the normalised failure
--     signature (digits/ids stripped, lowercased) so identical failures group.
-- (2) certidao_emissao_aprendizados: append-only EVENTS — each time the system
--     reclassifies a failure signature (unknown→pcen / →transitoria), so we can
--     see WHEN it learned what. The latest row per (org, tipo, assinatura) is
--     the class `service._precisa_segunda_via` acts on.
-- (3) certidao_resultados.pcen_*: the operator's acknowledgment of a Receita
--     "positiva com efeitos de negativa" 2ª via (who/when/which validity), or
--     their "tenho dúvida". Re-processing the row clears them in application
--     code; a different printed validity never matches the acknowledged one.
--
-- Forward-only, idempotent. 🔴 MIGRATION FILE ONLY — applying is the
-- tech-lead's + user's decision.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.certidao_emissao_observacoes (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                    UUID NOT NULL,
    consulta_id               UUID REFERENCES social_wiring.certidao_consultas (id) ON DELETE SET NULL,
    resultado_id              UUID REFERENCES social_wiring.certidao_resultados (id) ON DELETE SET NULL,
    tipo                      TEXT NOT NULL,
    provider                  TEXT NOT NULL DEFAULT 'infosimples',
    endpoint                  TEXT NOT NULL,
    documento_tipo            TEXT,
    documento_hash            TEXT,
    params                    JSONB NOT NULL DEFAULT '{}'::jsonb,
    tentativa                 INTEGER NOT NULL DEFAULT 1,
    preferencia_emissao       TEXT,
    http_status               INTEGER,
    code                      INTEGER,
    code_message              TEXT,
    errors                    JSONB NOT NULL DEFAULT '[]'::jsonb,
    sucesso                   BOOLEAN NOT NULL DEFAULT false,
    data_tipo                 TEXT,
    data_situacao             TEXT,
    emissao_data              DATE,
    validade                  DATE,
    validade_prorrogada       DATE,
    conseguiu_emitir_negativa BOOLEAN,
    elapsed_ms                INTEGER,
    price_brl                 NUMERIC(10, 4),
    billable                  BOOLEAN,
    fallback_de               UUID REFERENCES social_wiring.certidao_emissao_observacoes (id) ON DELETE SET NULL,
    assinatura                TEXT,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_cert_obs_org_tipo_created
    ON social_wiring.certidao_emissao_observacoes (org_id, tipo, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sw_cert_obs_documento
    ON social_wiring.certidao_emissao_observacoes (org_id, tipo, documento_hash, created_at DESC)
    WHERE documento_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sw_cert_obs_assinatura
    ON social_wiring.certidao_emissao_observacoes (org_id, tipo, assinatura)
    WHERE assinatura IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sw_cert_obs_fallback
    ON social_wiring.certidao_emissao_observacoes (fallback_de)
    WHERE fallback_de IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sw_cert_obs_resultado
    ON social_wiring.certidao_emissao_observacoes (resultado_id)
    WHERE resultado_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sw_cert_obs_consulta
    ON social_wiring.certidao_emissao_observacoes (consulta_id)
    WHERE consulta_id IS NOT NULL;

ALTER TABLE social_wiring.certidao_emissao_observacoes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "certidao_emissao_observacoes_select_own_org"
    ON social_wiring.certidao_emissao_observacoes;
CREATE POLICY "certidao_emissao_observacoes_select_own_org"
    ON social_wiring.certidao_emissao_observacoes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "certidao_emissao_observacoes_service_role"
    ON social_wiring.certidao_emissao_observacoes;
CREATE POLICY "certidao_emissao_observacoes_service_role"
    ON social_wiring.certidao_emissao_observacoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE social_wiring.certidao_emissao_observacoes IS
    'One row per InfoSimples call (every tipo, success or failure) — the '
    'emission watcher. No token/birthdate/name/full document (LGPD). Migration 186.';

CREATE TABLE IF NOT EXISTS social_wiring.certidao_emissao_aprendizados (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    tipo           TEXT NOT NULL,
    assinatura     TEXT NOT NULL,
    -- 'pcen' | 'transitoria' | 'desconhecida' — a closed set owned by
    -- `aprendizado.classificar` (no CHECK: a declared guard needs a behaviour
    -- probe in verify_db_guards, and this vocabulary is not a safety boundary).
    classe         TEXT NOT NULL,
    classe_anterior TEXT,
    evidencia      JSONB NOT NULL DEFAULT '{}'::jsonb,
    primeira_obs_em TIMESTAMPTZ,
    ultima_obs_em   TIMESTAMPTZ,
    decidido_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_cert_aprend_chave
    ON social_wiring.certidao_emissao_aprendizados (org_id, tipo, assinatura, decidido_em DESC);

ALTER TABLE social_wiring.certidao_emissao_aprendizados ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "certidao_emissao_aprendizados_select_own_org"
    ON social_wiring.certidao_emissao_aprendizados;
CREATE POLICY "certidao_emissao_aprendizados_select_own_org"
    ON social_wiring.certidao_emissao_aprendizados
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "certidao_emissao_aprendizados_service_role"
    ON social_wiring.certidao_emissao_aprendizados;
CREATE POLICY "certidao_emissao_aprendizados_service_role"
    ON social_wiring.certidao_emissao_aprendizados
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE social_wiring.certidao_emissao_aprendizados IS
    'Append-only reclassification events of InfoSimples failure signatures '
    '(unknown→pcen / →transitoria). Latest row per (org,tipo,assinatura) is the '
    'class the 2ª-via trigger acts on. Migration 186.';

-- ── Receita PCEN acknowledgment, per resultado ───────────────────────────
ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS pcen_ciente_por      UUID,
    ADD COLUMN IF NOT EXISTS pcen_ciente_em       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS pcen_ciente_validade DATE,
    ADD COLUMN IF NOT EXISTS pcen_duvida_por      UUID,
    ADD COLUMN IF NOT EXISTS pcen_duvida_em       TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.certidao_resultados.pcen_ciente_validade IS
    'The printed validity the operator acknowledged ("Entendi — seguir com esta '
    'certidão"). Valid only while it equals validade_ate; cleared on re-processing. '
    'Migration 186.';

NOTIFY pgrst, 'reload schema';
