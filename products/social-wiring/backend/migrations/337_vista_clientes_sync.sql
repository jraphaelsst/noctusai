-- ============================================================================
-- Migration 337 -- social_wiring: Vista clientes -> our lead people, fill-empty-only (owner 2026-11-09)
-- ============================================================================
-- Owner: "sync our lead data with theirs. they only add to leads, divergencies get warned but never overwritten."
-- The flow is ONE WAY (Vista -> us): Vista values fill EMPTY columns of `social_wiring.clientes` (the canonical person layer of a
-- lead, keyed by `chave_canonica` = leads.contato_norm); a different non-empty value is NEVER overwritten -- it becomes a pending row in
-- `vista_cliente_avisos` (sibling of lead_corretor_divergencias / imovel_ref_avisos). Nothing is ever written to Vista.
--   vista_cliente_links          lead person <-> Vista cliente Codigo (so later runs are incremental)
--   vista_cliente_avisos         divergence / ambiguous-match warnings (one OPEN row per subject+campo)
--   vista_clientes_sync_estado   per-org settings + last run (the per-org Vista rate budget, the LGPD identity flag)
-- FORWARD-ONLY, IDEMPOTENT, backward-compatible with the previous image (new tables only). Backend-only: RLS on, service role only.
-- ============================================================================

SET search_path = social_wiring, public;

CREATE TABLE IF NOT EXISTS social_wiring.vista_cliente_links (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid        NOT NULL,
    cliente_id     uuid        NOT NULL REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    vista_codigo   text        NOT NULL,
    casado_por     text        NOT NULL CHECK (casado_por IN ('cpf', 'telefone', 'email')),
    flags          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    campos_preenchidos text[]  NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now(),
    ultima_sync_em timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_vista_cliente_links_codigo ON social_wiring.vista_cliente_links (org_id, vista_codigo);
CREATE INDEX IF NOT EXISTS idx_sw_vista_cliente_links_cliente ON social_wiring.vista_cliente_links (org_id, cliente_id);

CREATE TABLE IF NOT EXISTS social_wiring.vista_cliente_avisos (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid        NOT NULL,
    tipo           text        NOT NULL CHECK (tipo IN ('campo_divergente', 'match_ambiguo')),
    status         text        NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'resolvida', 'ignorada')),
    vista_codigo   text        NOT NULL,
    cliente_id     uuid        REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    campo          text        NOT NULL DEFAULT '',
    -- the two values, so a human can decide. CPF / RG are stored MASKED (last 3) -- never the raw document number.
    valor_nosso    text,
    valor_vista    text,
    candidatos     uuid[],
    nota           text,
    notificado_em  timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    resolvido_em   timestamptz,
    resolvido_por  uuid
);
-- one OPEN notice per (Vista cliente, our person, campo, tipo): a re-run never duplicates and never re-warns
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_vista_cliente_avisos_aberto
    ON social_wiring.vista_cliente_avisos (org_id, tipo, vista_codigo, campo, COALESCE(cliente_id::text, ''))
    WHERE status = 'pendente';
CREATE INDEX IF NOT EXISTS idx_sw_vista_cliente_avisos_lista ON social_wiring.vista_cliente_avisos (org_id, tipo, status, created_at DESC);

CREATE TABLE IF NOT EXISTS social_wiring.vista_clientes_sync_estado (
    org_id               uuid        PRIMARY KEY,
    -- the Vista request budget of THIS org (requests/second). NULL = the platform default (bucket `vista`: 5 rps, burst 10).
    vista_rps            numeric     CHECK (vista_rps IS NULL OR (vista_rps >= 0.2 AND vista_rps <= 10)),
    -- LGPD gate: CPF / RG are brought from Vista only while this is true. DEFAULT OFF -- the owner turns it on after the legal read.
    importar_identidade  boolean     NOT NULL DEFAULT false,
    ultimo_cursor        text,
    ultima_execucao_em   timestamptz,
    ultimo_resumo        jsonb,
    updated_at           timestamptz NOT NULL DEFAULT now(),
    updated_by           uuid
);

ALTER TABLE social_wiring.vista_cliente_links ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS vista_cliente_links_service_role ON social_wiring.vista_cliente_links;
CREATE POLICY vista_cliente_links_service_role ON social_wiring.vista_cliente_links
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.vista_cliente_links FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE social_wiring.vista_cliente_links TO service_role;
COMMENT ON TABLE social_wiring.vista_cliente_links IS 'tier:org';

ALTER TABLE social_wiring.vista_cliente_avisos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS vista_cliente_avisos_service_role ON social_wiring.vista_cliente_avisos;
CREATE POLICY vista_cliente_avisos_service_role ON social_wiring.vista_cliente_avisos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.vista_cliente_avisos FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE social_wiring.vista_cliente_avisos TO service_role;
COMMENT ON TABLE social_wiring.vista_cliente_avisos IS 'tier:org';

ALTER TABLE social_wiring.vista_clientes_sync_estado ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS vista_clientes_sync_estado_service_role ON social_wiring.vista_clientes_sync_estado;
CREATE POLICY vista_clientes_sync_estado_service_role ON social_wiring.vista_clientes_sync_estado
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL ON TABLE social_wiring.vista_clientes_sync_estado FROM PUBLIC, anon, authenticated;
GRANT ALL ON TABLE social_wiring.vista_clientes_sync_estado TO service_role;
COMMENT ON TABLE social_wiring.vista_clientes_sync_estado IS 'tier:org';

