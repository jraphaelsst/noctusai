-- 124_fotos_referencias_guias.sql -- social_wiring: global reference pool
-- + style guides (PLATFORM SCOPE — documented exception)
--
-- 🔴 These two tables carry NO org_id -- they are a single, GLOBAL company
-- pool + guide, same documented platform-wide-taxonomy exception pattern
-- as `social_wiring.status_pagina` (036) and `social_wiring.cliente_
-- documento_tipos` (057): shared by every org, not per-tenant data. This
-- is a deliberate deviation from the "every table gets org_id" convention
-- and is called out explicitly here rather than silently missing a
-- column reviewers would otherwise flag.
--
-- Contract §5/§6 (projects/edicao-fotos/EDICAO-FOTOS-CONTRACT.md):
--   - Reference pool CRUD + guide activation: platform admin + photo
--     curator ONLY (role matrix). RLS below grants broad SELECT (everyone
--     needs to read the active guide/pool) and restricts mutation to
--     service_role -- the curator/platform-admin gate is enforced at the
--     API layer via `noctusai_lib.api.auth.platform.require_permission`
--     ('photo_curator') / `require_platform_admin`, both already shipped
--     (S6, this project's Wave 1). This is the SAME shape
--     `cliente_documento_tipos` uses (057): "readable by every
--     authenticated user, platform-wide, same as reading an enum."
--   - "delete" a reference pair = ARCHIVE (arquivado_em set), kept for
--     history, no longer counted toward the pool limit.
--   - Guide versions are IMMUTABLE once created; "restaurar" clones the
--     old version as a NEW version (never an UPDATE of an old row).
--   - At most one guide version may be `status='ativa'` at a time --
--     enforced by a partial unique index, not application convention.
--
-- FORWARD-ONLY. MIGRATION FILE ONLY -- not applied to any database by this
-- change. Applying needs owner consent.

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. fotos_referencias -- before/after reference pairs
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_referencias (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    antes_url      TEXT NOT NULL,
    depois_url     TEXT NOT NULL,
    -- Fixed room/area vocabulary (plan §1: "tagged room/area (fixed list)").
    comodo         TEXT NOT NULL CHECK (comodo IN (
        'sala', 'quarto', 'cozinha', 'banheiro', 'area_externa',
        'fachada', 'varanda', 'escritorio', 'outro'
    )),
    tipos_edicao   TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
        CHECK (tipos_edicao <@ ARRAY['cor_luz', 'ceu', 'declutter', 'staging_virtual']::TEXT[]),
    nota           TEXT,
    criado_por     UUID NOT NULL,
    -- "delete" = archive (contract §5). Archived rows are kept for
    -- history and excluded from the pool-limit count via the partial
    -- index below.
    arquivado_em   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The pool-limit check's read path: count of active (non-archived) pairs.
CREATE INDEX IF NOT EXISTS ix_fotos_referencias_ativas
    ON social_wiring.fotos_referencias (arquivado_em)
    WHERE arquivado_em IS NULL;
CREATE INDEX IF NOT EXISTS ix_fotos_referencias_comodo
    ON social_wiring.fotos_referencias (comodo)
    WHERE arquivado_em IS NULL;

ALTER TABLE social_wiring.fotos_referencias ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fotos_referencias_select_authenticated" ON social_wiring.fotos_referencias
    FOR SELECT TO authenticated
    USING (true);

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_referencias
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE social_wiring.fotos_referencias IS
    'Global (platform-scope, no org_id) before/after reference pool. CRUD gated at the API layer by require_permission(photo_curator) / require_platform_admin.';

-- ----------------------------------------------------------------------------
-- 2. fotos_guias_estilo -- versioned, AI-written style guide
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS social_wiring.fotos_guias_estilo (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    versao              INTEGER NOT NULL,
    texto                TEXT NOT NULL,
    sha256                TEXT NOT NULL,
    -- Every new version is a DRAFT until a platform admin or curator
    -- activates it (contract §6). 'substituida' = a formerly-active
    -- version that has since been superseded by a newer activation.
    status                TEXT NOT NULL DEFAULT 'rascunho'
        CHECK (status IN ('rascunho', 'ativa', 'substituida')),
    -- Set only when this version was produced via "restaurar" (clone an
    -- old version as new) -- versions themselves stay immutable.
    gerado_de_versao      INTEGER,
    criado_por            UUID,   -- NULL when auto-generated (debounced regen after pool changes)
    ativado_por           UUID,
    ativado_em            TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (versao)
);

-- At most one 'ativa' row at a time -- a genuine DB constraint, not a
-- convention the API layer merely happens to follow. Constant-expression
-- partial unique index: every row where status='ativa' indexes to the
-- literal `true`, so a second such row collides.
CREATE UNIQUE INDEX IF NOT EXISTS ux_fotos_guias_estilo_uma_ativa
    ON social_wiring.fotos_guias_estilo ((true))
    WHERE status = 'ativa';

ALTER TABLE social_wiring.fotos_guias_estilo ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fotos_guias_estilo_select_authenticated" ON social_wiring.fotos_guias_estilo
    FOR SELECT TO authenticated
    USING (true);

CREATE POLICY "service_role_bypass" ON social_wiring.fotos_guias_estilo
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMENT ON TABLE social_wiring.fotos_guias_estilo IS
    'Global (platform-scope, no org_id) versioned style guide. Versions are immutable; restore clones as a new version. At most one status=ativa row.';
