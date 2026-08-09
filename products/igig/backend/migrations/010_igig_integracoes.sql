-- ============================================================================
-- IgIg — Integrações de canal (Módulo 5 shell)
--
-- Per-org credentials for the social channels. The TOKEN is encrypted with the
-- seed's Fernet helper before it ever reaches this table — same treatment as
-- the Cofre de Acessos, and for the same reason: if a backup or replica leaks,
-- the tokens are not recoverable without the key, which lives out-of-band.
--
-- Deliberately a product table rather than writes into core's `org_settings`:
-- `resolve_credential()` READS that table, but it is owned by core, and IgIg
-- writing another product's schema would couple their migrations. Reads can
-- still fall through to the platform chain later without changing this shape.
--
-- SQLite mirror: migrations/sqlite/010_integracoes.sql (parity-tested).
-- ============================================================================
SET search_path = igig, public;

CREATE TABLE IF NOT EXISTS igig.integracao (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    canal         TEXT NOT NULL
                  CHECK (canal IN ('instagram', 'facebook', 'tiktok', 'linkedin')),
    -- Fernet ciphertext. There is no plaintext column, by design.
    token_cifrado TEXT,
    -- The handle/page the token authorises, for display. NOT a secret.
    conta_externa TEXT,
    conectado_em  TIMESTAMPTZ,
    -- Set when a publish attempt fails auth, so the UI can say "reconnect"
    -- instead of leaving an operator guessing why posts stopped.
    ultimo_erro   TEXT,
    ativo         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_integracao_org ON igig.integracao (org_id);
-- One credential per channel per org.
CREATE UNIQUE INDEX IF NOT EXISTS idx_igig_integracao_canal
    ON igig.integracao (org_id, canal);

ALTER TABLE igig.integracao ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS integracao_org_isolation ON igig.integracao;
CREATE POLICY integracao_org_isolation ON igig.integracao
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

DROP TRIGGER IF EXISTS trg_integracao_updated_at ON igig.integracao;
CREATE TRIGGER trg_integracao_updated_at
    BEFORE UPDATE ON igig.integracao
    FOR EACH ROW EXECUTE FUNCTION igig.set_updated_at();
