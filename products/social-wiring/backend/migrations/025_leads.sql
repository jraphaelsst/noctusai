-- 025_leads.sql — Leads module: canonical dimensions + fact table +
-- import provenance.
--
-- Domain: products/social-wiring/projects/leads-module-PROJECT.md §3/§4.
-- Turns the 29-sheet "CONTROLE LEADS" spreadsheet into a first-class
-- managed surface. `lead_sources` / `lead_corretores` are the canonical
-- dimensions; `lead_source_aliases` / `lead_corretor_aliases` are the
-- EDITABLE normalization maps a raw spreadsheet spelling resolves
-- through (e.g. "VIVAREAL" / "VILA REAL" / "VR" -> the one `viva-real`
-- source row). `leads` is the fact table; `lead_import_batches` is
-- import provenance/audit.
--
-- RLS shape mirrors 020_instagram_metric_snapshots.sql (the newest
-- CREATE-TABLE-with-RLS migration at authoring time): authenticated
-- reads via `public.current_org_id()` (SECURITY DEFINER — NEVER
-- `auth.jwt()` top-level or `user_metadata`, both either always-null or
-- user-editable, per `memory/feedback_rls_never_key_on_user_metadata.md`);
-- service_role ALL (backend writes go through the admin client).
--
-- PREREQUISITE: public.current_org_id() defined in 011_rls_current_org_id.sql.
-- Forward-only + idempotent (CREATE TABLE IF NOT EXISTS / DROP POLICY IF
-- EXISTS + CREATE POLICY).
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply
-- via noctus.dev.migrate_product with explicit tech-lead consent.
--
-- NOTE on seed data (deviation from the brief's "seed lead_sources +
-- lead_source_aliases in this migration" instruction): `lead_sources` /
-- `lead_corretores` / their alias tables are `org_id NOT NULL` (per-org
-- dimensions) and no migration in this product ever seeds an org-scoped
-- row with a hardcoded `org_id` — there is no "the org" at migration-apply
-- time in a multi-tenant schema, and picking one real org's UUID here
-- would silently starve every OTHER org of the canonical catalog forever.
-- The canonical source/alias/corretor/alias catalog (derived from reading
-- the real workbook) instead lives as Python constants in
-- `app/modules/leads/seed_data.py` and is upserted idempotently, per-org,
-- by `dimensions_service.ensure_default_dimensions(org_id)` — called at
-- the top of `POST /api/leads/import/commit` (a real write already) and
-- NOT from a bare GET. See that module's docstring for the full data
-- provenance. This changes WHERE the seed rows are written, not the
-- table shapes or the `/api/leads/*` response contract (§5 is untouched).

SET search_path = social_wiring, public;

-- ── lead_sources — canonical origem dimension ──────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.lead_sources (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    slug        TEXT NOT NULL,
    label       TEXT NOT NULL,
    categoria   TEXT NOT NULL DEFAULT 'outro'
                CHECK (categoria IN ('portal', 'social', 'direto', 'parceria', 'offline', 'outro')),
    cor         TEXT,
    ativo       BOOLEAN NOT NULL DEFAULT true,
    ordem       INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ,
    UNIQUE (org_id, slug)
);

ALTER TABLE social_wiring.lead_sources ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lead_sources_select_own_org" ON social_wiring.lead_sources;
CREATE POLICY "lead_sources_select_own_org" ON social_wiring.lead_sources
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_sources_service_role" ON social_wiring.lead_sources;
CREATE POLICY "lead_sources_service_role" ON social_wiring.lead_sources
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── lead_source_aliases — the editable normalization map ───────────────
CREATE TABLE IF NOT EXISTS social_wiring.lead_source_aliases (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    alias       TEXT NOT NULL,
    alias_norm  TEXT NOT NULL,
    source_id   UUID NOT NULL REFERENCES social_wiring.lead_sources(id) ON DELETE CASCADE,
    origem      TEXT NOT NULL DEFAULT 'seed' CHECK (origem IN ('seed', 'import', 'manual')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, alias_norm)
);

ALTER TABLE social_wiring.lead_source_aliases ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lead_source_aliases_select_own_org" ON social_wiring.lead_source_aliases;
CREATE POLICY "lead_source_aliases_select_own_org" ON social_wiring.lead_source_aliases
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_source_aliases_service_role" ON social_wiring.lead_source_aliases;
CREATE POLICY "lead_source_aliases_service_role" ON social_wiring.lead_source_aliases
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_lead_source_aliases_source
    ON social_wiring.lead_source_aliases (org_id, source_id);

-- ── lead_corretores — broker dimension ──────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.lead_corretores (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    nome        TEXT NOT NULL,
    nome_norm   TEXT NOT NULL,
    cor         TEXT,
    ativo       BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ,
    UNIQUE (org_id, nome_norm)
);

ALTER TABLE social_wiring.lead_corretores ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lead_corretores_select_own_org" ON social_wiring.lead_corretores;
CREATE POLICY "lead_corretores_select_own_org" ON social_wiring.lead_corretores
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_corretores_service_role" ON social_wiring.lead_corretores;
CREATE POLICY "lead_corretores_service_role" ON social_wiring.lead_corretores
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── lead_corretor_aliases ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.lead_corretor_aliases (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    alias        TEXT NOT NULL,
    alias_norm   TEXT NOT NULL,
    corretor_id  UUID NOT NULL REFERENCES social_wiring.lead_corretores(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, alias_norm)
);

ALTER TABLE social_wiring.lead_corretor_aliases ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lead_corretor_aliases_select_own_org" ON social_wiring.lead_corretor_aliases;
CREATE POLICY "lead_corretor_aliases_select_own_org" ON social_wiring.lead_corretor_aliases
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_corretor_aliases_service_role" ON social_wiring.lead_corretor_aliases;
CREATE POLICY "lead_corretor_aliases_service_role" ON social_wiring.lead_corretor_aliases
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_lead_corretor_aliases_corretor
    ON social_wiring.lead_corretor_aliases (org_id, corretor_id);

-- ── lead_import_batches — provenance / audit ────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.lead_import_batches (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    filename       TEXT NOT NULL,
    sheets         INTEGER NOT NULL DEFAULT 0,
    rows_read      INTEGER NOT NULL DEFAULT 0,
    rows_inserted  INTEGER NOT NULL DEFAULT 0,
    rows_updated   INTEGER NOT NULL DEFAULT 0,
    rows_skipped   INTEGER NOT NULL DEFAULT 0,
    rows_flagged   INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'erro')),
    erro           TEXT,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at    TIMESTAMPTZ,
    created_by     UUID
);

ALTER TABLE social_wiring.lead_import_batches ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "lead_import_batches_select_own_org" ON social_wiring.lead_import_batches;
CREATE POLICY "lead_import_batches_select_own_org" ON social_wiring.lead_import_batches
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "lead_import_batches_service_role" ON social_wiring.lead_import_batches;
CREATE POLICY "lead_import_batches_service_role" ON social_wiring.lead_import_batches
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_lead_import_batches_org_started
    ON social_wiring.lead_import_batches (org_id, started_at DESC);

-- ── leads — the fact table ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.leads (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    data_entrada      DATE NOT NULL,
    ano               SMALLINT GENERATED ALWAYS AS (EXTRACT(YEAR  FROM data_entrada)) STORED,
    mes               SMALLINT GENERATED ALWAYS AS (EXTRACT(MONTH FROM data_entrada)) STORED,
    codigo_raw        TEXT,
    codigo_imovel     TEXT,
    empreendimento    TEXT,
    regiao            TEXT,
    origem_id         UUID REFERENCES social_wiring.lead_sources(id) ON DELETE SET NULL,
    origem_raw        TEXT,
    tipo_lead         TEXT NOT NULL DEFAULT 'desconhecido'
                      CHECK (tipo_lead IN ('novo', 'retorno', 'desconhecido')),
    cliente_nome      TEXT,
    contato           TEXT,
    contato_tipo      TEXT CHECK (contato_tipo IN ('telefone', 'email', 'desconhecido')),
    contato_norm      TEXT,
    corretor_id       UUID REFERENCES social_wiring.lead_corretores(id) ON DELETE SET NULL,
    corretor_raw      TEXT,
    anuncio_tier      TEXT CHECK (anuncio_tier IN ('simples', 'destaque', 'super_destaque')),
    status            TEXT,
    observacoes       TEXT,
    follow_up_data    DATE,
    follow_up_nota    TEXT,
    -- unmapped/ambiguous origem (incl. a código string that leaked into
    -- the origem column) — NOT set for unparseable-date rows, which are
    -- skipped entirely rather than inserted (see the importer).
    needs_review      BOOLEAN NOT NULL DEFAULT false,
    source_sheet      TEXT,
    source_row        INTEGER,
    import_batch_id   UUID REFERENCES social_wiring.lead_import_batches(id) ON DELETE SET NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ
);

-- Idempotency key for the import: re-running upserts instead of
-- duplicating. Manually-created leads have `source_sheet IS NULL` and
-- are exempt (partial unique index).
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_leads_org_sheet_row
    ON social_wiring.leads (org_id, source_sheet, source_row)
    WHERE source_sheet IS NOT NULL;

ALTER TABLE social_wiring.leads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "leads_select_own_org" ON social_wiring.leads;
CREATE POLICY "leads_select_own_org" ON social_wiring.leads
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "leads_service_role" ON social_wiring.leads;
CREATE POLICY "leads_service_role" ON social_wiring.leads
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_sw_leads_org_data_entrada
    ON social_wiring.leads (org_id, data_entrada DESC);
CREATE INDEX IF NOT EXISTS idx_sw_leads_org_ano_mes
    ON social_wiring.leads (org_id, ano, mes);
CREATE INDEX IF NOT EXISTS idx_sw_leads_org_origem
    ON social_wiring.leads (org_id, origem_id);
CREATE INDEX IF NOT EXISTS idx_sw_leads_org_corretor
    ON social_wiring.leads (org_id, corretor_id);
CREATE INDEX IF NOT EXISTS idx_sw_leads_org_empreendimento
    ON social_wiring.leads (org_id, empreendimento);
CREATE INDEX IF NOT EXISTS idx_sw_leads_org_needs_review
    ON social_wiring.leads (org_id, needs_review) WHERE needs_review;

-- Free-text search over cliente_nome (the `q` filter, §5.1). GIN trigram
-- needs `pg_trgm`; enabled here if available. If the extension cannot be
-- created (no superuser / not whitelisted on this Postgres), the index
-- creation is skipped loudly (RAISE NOTICE) and the `q` filter falls back
-- to plain `ILIKE` at query time (see `services/query.py`) — no silent
-- failure, just a documented perf fallback.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
EXCEPTION WHEN insufficient_privilege OR feature_not_supported THEN
    RAISE NOTICE 'pg_trgm unavailable — lead_sources.cliente_nome search falls back to ILIKE (no trigram index)';
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        CREATE INDEX IF NOT EXISTS idx_sw_leads_cliente_nome_trgm
            ON social_wiring.leads USING gin (cliente_nome gin_trgm_ops);
    ELSE
        RAISE NOTICE 'pg_trgm not installed — skipping idx_sw_leads_cliente_nome_trgm (ILIKE fallback in app code)';
    END IF;
END $$;

-- ── DEFERRED: vendas / fechamento ────────────────────────────────
--   lead_vendas(id, org_id, lead_id?, origem_id, empreendimento, unidade,
--               data_venda, valor, corretor_id)  → conversão lead→venda
-- ── DEFERRED: campanhas / METRICAS ───────────────────────────────
--   lead_campanhas(id, org_id, origem_id, periodo_inicio, periodo_fim,
--                  investimento, impressoes, cliques, cpc, leads, cpl,
--                  visitas_perfil, custo_visita, engajamento)  → CPL / ROI
