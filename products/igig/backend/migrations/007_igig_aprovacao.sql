-- ============================================================================
-- IgIg — Portal de Aprovação Externo (Módulo 4)
--
-- One approval link per tarefa sent to the agency's client. The TOKEN IS THE
-- AUTH: the portal is unauthenticated by design (the client has no noc
-- account), so the token must be unguessable, expirable, and single-decision.
-- Mirrors the shape Orbity already ships (`/aprovar/:token`), so the eventual
-- IgIg→Orbity merge does not have to reconcile two different portals.
--
-- Read path deliberately runs on the service-role client and therefore
-- BYPASSES RLS — an anonymous caller has no org. Security is: the token must
-- exist, not be expired, and not already be decided. The RLS policy below
-- still governs every AUTHENTICATED access (the agency's own team).
--
-- SQLite mirror: migrations/sqlite/002_aprovacao.sql (parity-tested).
-- ============================================================================
SET search_path = igig, public;

CREATE TABLE IF NOT EXISTS igig.aprovacao (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    tarefa_id    UUID NOT NULL REFERENCES igig.tarefa (id) ON DELETE CASCADE,
    -- Unguessable by construction. Not the row id: leaking a sequential or
    -- otherwise inferable id would expose every client's content.
    token        TEXT NOT NULL UNIQUE,
    expira_em    TIMESTAMPTZ,
    -- NULL until the client acts. Non-NULL makes the link spent.
    decidido_em  TIMESTAMPTZ,
    decisao      TEXT CHECK (decisao IN ('aprovado', 'ajuste')),
    observacao   TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_igig_aprovacao_org ON igig.aprovacao (org_id);
CREATE INDEX IF NOT EXISTS idx_igig_aprovacao_tarefa ON igig.aprovacao (org_id, tarefa_id);
-- The public lookup is by token alone (no org in scope) — it must be indexed
-- and unique. UNIQUE on the column already provides the index; named here for
-- symmetry with the SQLite mirror.

ALTER TABLE igig.aprovacao ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS aprovacao_org_isolation ON igig.aprovacao;
CREATE POLICY aprovacao_org_isolation ON igig.aprovacao
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

DROP TRIGGER IF EXISTS trg_aprovacao_updated_at ON igig.aprovacao;
CREATE TRIGGER trg_aprovacao_updated_at
    BEFORE UPDATE ON igig.aprovacao
    FOR EACH ROW EXECUTE FUNCTION igig.set_updated_at();
