-- 125_fotos_aprendizado.sql -- social_wiring: per-org learning loop
-- (AI-proposed "don't do this" rules + effective-guide snapshots)
--
-- Plan §1: "AI proposes 'don't' rules from that agency's rejection
-- comments; approved by platform admin or agency admin; only the platform
-- admin can override an agency admin's decision. Effective guide = active
-- company guide + that org's approved rules (versioned)."
--
-- 🔴 THE OVERRIDE TRIGGER'S DESIGN (read before touching this file):
-- writes in this codebase run through the backend's SERVICE-ROLE admin
-- client (same convention as `cliente_documentos` / `llm_usage` /
-- `jobs` elsewhere in this product) -- `auth.uid()` is NULL under
-- service_role, so a trigger that unconditionally required
-- `public.is_platform_admin()` would block EVERY write, including a
-- legitimate platform-admin override performed through the app-layer
-- `require_platform_admin` dependency. The trigger below therefore only
-- enforces the override rule when `(SELECT auth.uid()) IS NOT NULL` --
-- i.e. a request executing AS `authenticated` (a direct table write
-- bypassing the app's own role check). This is defense-in-depth against
-- THAT path; it trusts service-role callers to have already been gated
-- by `require_org_admin` / `require_platform_admin` before the DB is
-- reached, which is the same trust boundary `jobs.sql.template`'s RLS
-- comment documents ("service_role BYPASSES RLS -- backend writes are
-- unaffected").
--
-- Every org table: org_id + RLS org_id = public.current_org_id() +
-- service_role_bypass. No `authenticated` UPDATE/INSERT policy is granted
-- anywhere in this file -- approve/reject/propose flows are backend
-- service-role writes, app-layer role-gated (contract §7: platform admin
-- + agency admin only; corretor is not in the role matrix for `/regras`
-- at all, so SELECT is admin-tier-only too).
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. fotos_regras_org -- per-org proposed/approved/rejected rules
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_regras_org (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                    UUID NOT NULL,
    texto                     TEXT NOT NULL,
    -- The rejection-comment source(s) the proposer drew this rule from --
    -- an array of {decisao_id, comentario} snapshots, not live FKs (a
    -- decisao's comment can't change, but keeping the text here means a
    -- future purge of old decisoes never breaks this audit trail).
    origem_comentarios        JSONB NOT NULL DEFAULT '[]'::jsonb,
    status                    TEXT NOT NULL DEFAULT 'proposta'
        CHECK (status IN ('proposta', 'aprovada', 'rejeitada')),
    decidido_por              UUID,
    decidido_em               TIMESTAMPTZ,
    -- Set true by the trigger below the moment a SECOND decided-state
    -- change happens (i.e. someone is overriding a prior aprovada/
    -- rejeitada decision) -- an audit flag, independent of who performed
    -- the override.
    override_platform_admin   BOOLEAN NOT NULL DEFAULT false,
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fotos_regras_org_org_status
    ON social_wiring.fotos_regras_org (org_id, status);

-- The override guard -- see header. Also stamps updated_at and the
-- override flag; runs BEFORE UPDATE so NEW.* is what actually lands.
CREATE OR REPLACE FUNCTION social_wiring.fotos_regra_org_override_guard()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = social_wiring, public
AS $$
BEGIN
    IF (SELECT auth.uid()) IS NOT NULL
       AND OLD.status IN ('aprovada', 'rejeitada')
       AND NEW.status IN ('aprovada', 'rejeitada')
       AND NEW.status IS DISTINCT FROM OLD.status
       AND NOT public.is_platform_admin() THEN
        RAISE EXCEPTION 'Apenas o administrador da plataforma pode sobrepor uma decisao ja tomada'
            USING ERRCODE = '42501';
    END IF;

    IF OLD.status IN ('aprovada', 'rejeitada')
       AND NEW.status IN ('aprovada', 'rejeitada')
       AND NEW.status IS DISTINCT FROM OLD.status THEN
        NEW.override_platform_admin := true;
    END IF;

    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER fotos_regra_org_override_guard
    BEFORE UPDATE ON social_wiring.fotos_regras_org
    FOR EACH ROW EXECUTE FUNCTION social_wiring.fotos_regra_org_override_guard();

ALTER TABLE social_wiring.fotos_regras_org ENABLE ROW LEVEL SECURITY;

-- Admin-tier + platform-admin SELECT only -- corretor is absent from the
-- /regras role matrix entirely (contract §7).
CREATE POLICY "fotos_regras_org_select_admins" ON social_wiring.fotos_regras_org
    FOR SELECT TO authenticated
    USING (
        org_id = public.current_org_id()
        AND public.current_org_role() = ANY (ARRAY['owner', 'admin', 'manager'])
    );

CREATE POLICY "fotos_regras_org_select_platform_admin" ON social_wiring.fotos_regras_org
    FOR SELECT TO authenticated
    USING (public.is_platform_admin());

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_regras_org
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. fotos_conjuntos_regras -- versioned snapshot of an org's APPROVED
--    rule set (the training-dataset-stable unit the effective guide
--    references)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_conjuntos_regras (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    versao      INTEGER NOT NULL,
    regra_ids   UUID[] NOT NULL DEFAULT ARRAY[]::UUID[],
    sha256      TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, versao)
);

CREATE INDEX IF NOT EXISTS ix_fotos_conjuntos_regras_org
    ON social_wiring.fotos_conjuntos_regras (org_id, versao DESC);

ALTER TABLE social_wiring.fotos_conjuntos_regras ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fotos_conjuntos_regras_select_own_org" ON social_wiring.fotos_conjuntos_regras
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_conjuntos_regras
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. fotos_guias_efetivos -- effective guide per org (active company
--    guide + org's approved rule set), snapshotted at batch submit
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_guias_efetivos (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL,
    guia_estilo_id       UUID NOT NULL REFERENCES social_wiring.fotos_guias_estilo (id),
    conjunto_regras_id   UUID REFERENCES social_wiring.fotos_conjuntos_regras (id),
    texto                 TEXT NOT NULL,
    sha256                 TEXT NOT NULL,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, sha256)
);

CREATE INDEX IF NOT EXISTS ix_fotos_guias_efetivos_org_created
    ON social_wiring.fotos_guias_efetivos (org_id, created_at DESC);

ALTER TABLE social_wiring.fotos_guias_efetivos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fotos_guias_efetivos_select_own_org" ON social_wiring.fotos_guias_efetivos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_guias_efetivos
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 4. fotos_propostas_cursor -- per-org rule-proposer debounce cursor
--    (internal worker state -- service_role only, same "RLS ON, no
--    authenticated policy" shape as jobs.sql.template)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_propostas_cursor (
    org_id                   UUID PRIMARY KEY,
    ultima_decisao_id        UUID,
    ultima_execucao_em       TIMESTAMPTZ,
    rejeicoes_desde_ultima   INTEGER NOT NULL DEFAULT 0,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE social_wiring.fotos_propostas_cursor ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_propostas_cursor
    FOR ALL TO service_role USING (true) WITH CHECK (true);
