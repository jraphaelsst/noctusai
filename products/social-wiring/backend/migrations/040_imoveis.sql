-- 040_imoveis.sql — social_wiring.imoveis, the local mirror of the Vista catalog
--
-- Roadmap: project-history/roadmaps/social-wiring-imoveis-vista-2026-08.md (P2.2).
-- Shape derived from a full-catalog census of tenant `oneconsu-rest`
-- (2026-08-03): 1919 listar rows + 75 stratified detalhes payloads covering
-- all 20 categorias and all 3 statuses. Column nullability and the CHECK
-- constraints below are measured, not guessed — the census counts are cited
-- inline wherever a column looks over-permissive.
--
-- ── Q1: the primary key ────────────────────────────────────────────────
-- `(org_id, codigo)`. The census found ZERO duplicate `Codigo` across all
-- 1919 rows, so `codigo` is a safe natural key WITHIN a tenant — but it is
-- tenant-global, not globally unique, and every other social_wiring table is
-- org-scoped. A bare `codigo` PK would collide the moment a second org
-- connects a second Vista tenant that happens to use `CA0190` too.
-- No surrogate UUID: nothing references imóveis by FK yet, and `(org_id,
-- codigo)` is already the natural join target for `leads.codigo_imovel`.
--
-- ── There is deliberately NO `origem` column ───────────────────────────
-- An earlier draft carried `origem (vista|manual)` as a provenance flag.
-- That was wrong twice: Vista is THE source of truth for imóveis so there is
-- nothing to discriminate, and `origem` already means something else in this
-- schema — the marketing portal a LEAD came from (`lead_sources` /
-- `leads.origem_id`). Two different `origem`s in one schema would be worse
-- than a redundant column. Portal-vs-imóvel analysis joins through
-- `leads.codigo_imovel`, not through a column here.
--
-- RLS shape mirrors 025_leads.sql: authenticated reads via
-- `public.current_org_id()` (SECURITY DEFINER — NEVER `auth.jwt()`
-- top-level or `user_metadata`, both either always-null or user-editable),
-- service_role ALL for backend writes through the admin client.
--
-- PREREQUISITE: public.current_org_id() defined in 011_rls_current_org_id.sql.
-- Forward-only + idempotent (CREATE TABLE IF NOT EXISTS / DROP POLICY IF
-- EXISTS + CREATE POLICY).
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product with explicit tech-lead consent.

SET search_path = social_wiring, public;

-- ── imoveis — one row per Vista listing, per org ────────────────────────
CREATE TABLE IF NOT EXISTS social_wiring.imoveis (
    org_id              UUID        NOT NULL,
    codigo              TEXT        NOT NULL,

    -- Identidade.
    -- `codigo_imobiliaria` is NULLABLE by measurement: JSON null on 38/1919
    -- rows. NOT NULL here would reject 2% of the real catalog at sync time.
    codigo_imobiliaria  TEXT,

    -- Classificação.
    -- `status` is 100% populated across the census (Venda 89.4%,
    -- Venda e Aluguel 7.2%, Aluguel 3.4%) but is NOT constrained to those
    -- three: the value set is tenant-defined and a CHECK would turn a new
    -- tenant status into a hard sync failure. Same reasoning as the field
    -- calibration — do not freeze a tenant's vocabulary in our schema.
    titulo              TEXT,
    categoria           TEXT,
    status              TEXT,
    -- Derived transaction set. TEXT[] rather than an enum column for the
    -- same reason: `Venda e Aluguel` is genuinely both, so this is a set.
    finalidades         TEXT[]      NOT NULL DEFAULT '{}',

    -- Localização. `latitude`/`longitude` absent on 36.8% of the catalog —
    -- any map view needs a no-geo branch, this is not an anomaly.
    cep                 TEXT,
    logradouro          TEXT,
    numero              TEXT,
    complemento         TEXT,
    bairro              TEXT,
    cidade              TEXT,
    uf                  TEXT,
    empreendimento      TEXT,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,

    -- Comercial. NULL means "no price of this kind", which on the wire is
    -- spelled "0" (1488 rows) or "" (199 rows) — normalized before insert.
    -- A 0 here would be a bug, hence the CHECKs.
    valor_venda         NUMERIC(14, 2),
    valor_locacao       NUMERIC(14, 2),
    CONSTRAINT imoveis_valor_venda_not_zero   CHECK (valor_venda   IS NULL OR valor_venda   > 0),
    CONSTRAINT imoveis_valor_locacao_not_zero CHECK (valor_locacao IS NULL OR valor_locacao > 0),

    -- Dimensões. Same "0 means unknown" rule as money.
    -- `area_construida` is "0" on 1918/1919 rows — expect it near-empty.
    area_total          NUMERIC(12, 2),
    area_privativa      NUMERIC(12, 2),
    area_construida     NUMERIC(12, 2),
    CONSTRAINT imoveis_area_total_not_zero      CHECK (area_total      IS NULL OR area_total      > 0),
    CONSTRAINT imoveis_area_privativa_not_zero  CHECK (area_privativa  IS NULL OR area_privativa  > 0),
    CONSTRAINT imoveis_area_construida_not_zero CHECK (area_construida IS NULL OR area_construida > 0),

    -- Cômodos. Note these DO allow 0 — unlike money and area above. A
    -- Terreno genuinely has 0 dormitórios; that is data, not absence.
    -- Do not "harmonize" these CHECKs with the ones above.
    dormitorios         INTEGER,
    suites              INTEGER,
    vagas               INTEGER,
    CONSTRAINT imoveis_dormitorios_non_negative CHECK (dormitorios IS NULL OR dormitorios >= 0),
    CONSTRAINT imoveis_suites_non_negative      CHECK (suites      IS NULL OR suites      >= 0),
    CONSTRAINT imoveis_vagas_non_negative       CHECK (vagas       IS NULL OR vagas       >= 0),
    -- BOOLEAN, not a count. `Banheiros` (the count) is permission-denied on
    -- this tenant; `BanheiroSocial` is a "Sim"/"Nao" flag and was previously
    -- parsed as an int, yielding NULL on 100% of rows.
    banheiro_social     BOOLEAN,

    -- Mídia.
    foto_destaque       TEXT,
    fotos               TEXT[]      NOT NULL DEFAULT '{}',

    -- Atribuição. JSONB array, not a scalar: 252 imóveis (13.1%) carry 2-3
    -- corretores and the previous first-only read discarded the rest.
    corretores          JSONB       NOT NULL DEFAULT '[]'::jsonb,
    construtora         TEXT,

    -- Datas (Vista's own, not ours).
    data_cadastro       DATE,
    data_atualizacao    DATE,

    -- Características — slug set over a fixed 76-key tenant-wide schema.
    -- TEXT[] rather than 76 boolean columns: the key set is tenant-defined
    -- and drifts, so columns would need a migration per new amenity. A set
    -- also makes "quais imóveis têm piscina" a containment query (see the
    -- GIN index below).
    caracteristicas     TEXT[]      NOT NULL DEFAULT '{}',
    caracteristicas_raw JSONB       NOT NULL DEFAULT '{}'::jsonb,

    -- Auditoria. The verbatim merged listar+detalhes payload, so a modelling
    -- change can be re-derived without re-hitting Vista for 1919 imóveis.
    vista_raw           JSONB       NOT NULL DEFAULT '{}'::jsonb,

    -- Ours.
    sincronizado_em     TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (org_id, codigo)
);

ALTER TABLE social_wiring.imoveis ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "imoveis_select_own_org" ON social_wiring.imoveis;
CREATE POLICY "imoveis_select_own_org" ON social_wiring.imoveis
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "imoveis_service_role" ON social_wiring.imoveis;
CREATE POLICY "imoveis_service_role" ON social_wiring.imoveis
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ── Indexes — driven by the actual filter surface ──────────────────────
-- The census measured the cardinalities these serve: 20 categorias, 18
-- cidades, 428 bairros, 3 statuses.
CREATE INDEX IF NOT EXISTS idx_sw_imoveis_org_status
    ON social_wiring.imoveis (org_id, status);
CREATE INDEX IF NOT EXISTS idx_sw_imoveis_org_categoria
    ON social_wiring.imoveis (org_id, categoria);
CREATE INDEX IF NOT EXISTS idx_sw_imoveis_org_cidade_bairro
    ON social_wiring.imoveis (org_id, cidade, bairro);
CREATE INDEX IF NOT EXISTS idx_sw_imoveis_org_valor_venda
    ON social_wiring.imoveis (org_id, valor_venda);
-- Containment queries: "imóveis com piscina E churrasqueira".
CREATE INDEX IF NOT EXISTS idx_sw_imoveis_caracteristicas
    ON social_wiring.imoveis USING gin (caracteristicas);
CREATE INDEX IF NOT EXISTS idx_sw_imoveis_finalidades
    ON social_wiring.imoveis USING gin (finalidades);
-- Staleness sweep: "what did the last sync not touch?"
CREATE INDEX IF NOT EXISTS idx_sw_imoveis_sincronizado_em
    ON social_wiring.imoveis (org_id, sincronizado_em);

-- ── updated_at trigger ─────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION social_wiring.touch_imoveis_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_imoveis_updated_at ON social_wiring.imoveis;
CREATE TRIGGER trg_imoveis_updated_at
    BEFORE UPDATE ON social_wiring.imoveis
    FOR EACH ROW EXECUTE FUNCTION social_wiring.touch_imoveis_updated_at();

-- ── status_pagina — WITHOUT THIS THE NAV ITEM IS INVISIBLE ─────────────
-- The seed's `filterNavByPageStatus` gate hides a nav item that has no
-- matching status_pagina row, with NO error anywhere: the page and route
-- work if you type the URL, but the sidebar link never appears. Migrations
-- 018/021/023/039 all exist to close this same silent failure.
--
-- Seeded 'desenvolvimento', not 'producao' — the sync has not yet run
-- end-to-end against the live tenant from inside a container. Flip to
-- 'producao' once proven.
-- → KB § PATTERNS/frontend/status-pagina-dev-visibility.md
INSERT INTO social_wiring.status_pagina (nome_pagina, status) VALUES
    ('imoveis', 'desenvolvimento')
ON CONFLICT (nome_pagina) DO NOTHING;
