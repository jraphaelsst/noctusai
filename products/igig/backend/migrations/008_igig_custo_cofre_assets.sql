-- ============================================================================
-- IgIg — three decisions landed together (2026-08-09)
--
--   1. CUSTO/HORA (M1 calculator, M5 BI, M6 DRE) — role default + per-person
--      override. The spec says "tabela de custo/hora dos profissionais
--      cadastrados" but never defines it; this is the agreed model.
--   2. COFRE DE ACESSOS (M2) — client credentials encrypted at rest with the
--      seed's Fernet helper. The ciphertext lives here; the KEY never does.
--   3. VISUAL ASSETS (M4 portal) — peças stored through the seed's storage
--      seam; this table records the pointer, not the bytes.
--
-- SQLite mirror: migrations/sqlite/008_custo_cofre_assets.sql (parity-tested).
-- ============================================================================
SET search_path = igig, public;

-- ============================================================================
-- funcao — a role and its default hourly cost
--
-- Two-level model on purpose. A per-person-only table means every hire needs
-- a rate before their hours can be costed, and puts salary-derived numbers on
-- every row; a role-only table cannot tell a senior from a junior. Default
-- here, override on `profissional`, and `custo_hora_efetivo` resolves it.
-- ============================================================================
CREATE TABLE IF NOT EXISTS igig.funcao (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             UUID NOT NULL,
    nome               TEXT NOT NULL,
    custo_hora_padrao  NUMERIC(12, 2) NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_funcao_org ON igig.funcao (org_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_funcao_nome ON igig.funcao (org_id, nome);

-- ============================================================================
-- profissional — a team member, their função, and an optional rate override
--
-- `usuario_id` points at public.noctus_users. NOT a FK: that table lives in
-- another schema owned by core, and IgIg must not couple its migrations to
-- core's. Referential integrity is the app's job here.
-- ============================================================================
CREATE TABLE IF NOT EXISTS igig.profissional (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL,
    usuario_id           UUID,
    nome                 TEXT NOT NULL,
    funcao_id            UUID REFERENCES igig.funcao (id) ON DELETE SET NULL,
    -- NULL = inherit the função's default. 0 is a real value (an intern who
    -- costs nothing), so NULL and 0 must stay distinguishable.
    custo_hora_override  NUMERIC(12, 2),
    ativo                BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_profissional_org ON igig.profissional (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_profissional_usuario ON igig.profissional (org_id, usuario_id);

-- ============================================================================
-- acesso — Cofre de Acessos (M2)
--
-- `senha_cifrada` holds a Fernet token produced by
-- `noctusai_lib.security.encrypted_tokens.encrypt`, NEVER a plaintext
-- password. The key is resolved from configuration and lives OUT-OF-BAND from
-- this table by design: if a backup, replica or log line leaks these rows, the
-- credentials are not recoverable without it.
--
-- There is deliberately no plaintext column and no "reveal" flag — decryption
-- happens in process memory at the moment of use.
-- ============================================================================
CREATE TABLE IF NOT EXISTS igig.acesso (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    cliente_id     UUID NOT NULL REFERENCES igig.cliente (id) ON DELETE CASCADE,
    rotulo         TEXT NOT NULL,
    -- e.g. 'meta_business', 'tiktok_studio', 'drive', 'site'
    plataforma     TEXT,
    url            TEXT,
    usuario        TEXT,
    senha_cifrada  TEXT,
    observacoes    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_acesso_org ON igig.acesso (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_acesso_cliente ON igig.acesso (org_id, cliente_id);

-- ============================================================================
-- peca — the visual asset attached to a pauta (M4 portal, side-by-side view)
--
-- Stores a storage KEY, not bytes. The bytes live behind the seed's storage
-- seam (`noctusai_lib.integrations.storage`) — LocalFilesystemStorageBackend
-- in development, SupabaseStorageBackend in production — so this table does
-- not care which backend is mounted.
-- ============================================================================
CREATE TABLE IF NOT EXISTS igig.peca (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    pauta_id      UUID NOT NULL REFERENCES igig.pauta (id) ON DELETE CASCADE,
    storage_key   TEXT NOT NULL,
    nome_arquivo  TEXT,
    mime_type     TEXT,
    tamanho_bytes BIGINT,
    ordem         INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_peca_org ON igig.peca (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_peca_pauta ON igig.peca (org_id, pauta_id, ordem);

-- ============================================================================
-- RLS + updated_at triggers for the four new tables
-- ============================================================================
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['funcao', 'profissional', 'acesso', 'peca']
    LOOP
        EXECUTE format('ALTER TABLE igig.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON igig.%I', t || '_org_isolation', t);
        EXECUTE format(
            'CREATE POLICY %I ON igig.%I FOR ALL TO authenticated '
            'USING (org_id = public.current_org_id()) '
            'WITH CHECK (org_id = public.current_org_id())',
            t || '_org_isolation', t
        );
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON igig.%I', 'trg_' || t || '_updated_at', t);
        EXECUTE format(
            'CREATE TRIGGER %I BEFORE UPDATE ON igig.%I '
            'FOR EACH ROW EXECUTE FUNCTION igig.set_updated_at()',
            'trg_' || t || '_updated_at', t
        );
    END LOOP;
END $$;
