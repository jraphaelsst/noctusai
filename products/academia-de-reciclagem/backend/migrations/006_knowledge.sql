-- ============================================================================
-- Migration 006 — Julia/academia knowledge base (A.1–A.9)
--
-- Contract: projects/julia-agents-academia-CONTRACT.md §A. This migration
-- ships the DATA TABLES only (no revisions — A.10 + its triggers/functions
-- land in 007_revisions.sql, which is the natural dependency order:
-- kb_entries.current_revision_id needs kb_revisions to exist before its FK
-- can be attached).
--
-- Every table: id uuid pk, org_id uuid not null, created_at/updated_at,
-- RLS enabled with an org-scoped SELECT policy via public.current_org_id()
-- plus the literal `service_role_bypass` policy (keeper-detector coupling,
-- see noctusai_lib.sql.service_role_bypass). Routes call through the
-- ADMIN (service-role) client per contract §B.0 — RLS here is defence in
-- depth, never the authorization boundary; the app filters by org_id
-- explicitly on every query.
--
-- Field names stay PT-BR (contract §0) — Julia's tools are already written
-- against these names. Code identifiers are EN.
--
-- Forward-only + idempotent (CREATE TABLE IF NOT EXISTS / DROP POLICY IF
-- EXISTS before CREATE POLICY), matching the platform convention.
-- ============================================================================

-- ============================================================
-- Schema lock — pin name resolution to academia_de_reciclagem, public
-- WHY:
--   * RLS isolation: every product's tables live in its own
--     schema; un-locked search_path leaks resolution to
--     whatever the caller's session set.
--   * Cross-product safety: prevents accidental shadowing
--     when two products define identically-named helpers
--     (e.g. `current_org_id()`) in different schemas.
-- IDEMPOTENT: session-level setting; no DDL emitted.
-- ============================================================
SET search_path = academia_de_reciclagem, public;

-- ============================================================================
-- A.9 code_counters — declared FIRST: allocate_code() (007) reads/writes it,
-- and it has no FK dependency on anything else here.
-- ============================================================================

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.code_counters (
    org_id     UUID NOT NULL,
    prefix     TEXT NOT NULL,
    ultimo     INT  NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, prefix)
);

ALTER TABLE academia_de_reciclagem.code_counters ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "code_counters_select_own_org" ON academia_de_reciclagem.code_counters;
CREATE POLICY "code_counters_select_own_org" ON academia_de_reciclagem.code_counters
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.code_counters;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.code_counters FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION academia_de_reciclagem.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

CREATE OR REPLACE TRIGGER set_updated_at_code_counters
    BEFORE UPDATE ON academia_de_reciclagem.code_counters
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.set_updated_at();


-- ============================================================================
-- A.1 kb_entries
--
-- current_revision_id has NO fk yet — 007 attaches
-- `kb_entries_current_revision_id_fkey` once kb_revisions exists.
-- ============================================================================

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.kb_entries (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,
    slug                TEXT NOT NULL,
    categoria           TEXT NOT NULL CHECK (categoria IN (
                            'contexto', 'dominio', 'instrucoes', 'skills',
                            'workflows', 'mcp-servers', 'historico', 'marca',
                            'evals', 'geral'
                        )),
    subcategoria        TEXT,
    titulo              TEXT NOT NULL,
    resumo              TEXT,
    tags                TEXT[] NOT NULL DEFAULT '{}',
    corpo_md            TEXT NOT NULL,
    frontmatter         JSONB NOT NULL DEFAULT '{}',
    current_revision_id UUID,
    arquivado           BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT kb_entries_org_slug_unique UNIQUE (org_id, slug)
);

ALTER TABLE academia_de_reciclagem.kb_entries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "kb_entries_select_own_org" ON academia_de_reciclagem.kb_entries;
CREATE POLICY "kb_entries_select_own_org" ON academia_de_reciclagem.kb_entries
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.kb_entries;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.kb_entries FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE TRIGGER set_updated_at_kb_entries
    BEFORE UPDATE ON academia_de_reciclagem.kb_entries
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_kb_entries_org ON academia_de_reciclagem.kb_entries(org_id);
CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_kb_entries_categoria ON academia_de_reciclagem.kb_entries(org_id, categoria);


-- ============================================================================
-- A.2 decisions — append-only: a trigger below rejects DELETE outright and
-- rejects UPDATE of any column except `estado` and `superseded_by`.
-- ============================================================================

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.decisions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL,
    codigo                  TEXT NOT NULL,
    titulo                  TEXT NOT NULL,
    contexto                TEXT,
    decisao                 TEXT NOT NULL,
    motivo                  TEXT NOT NULL,
    alternativas_rejeitadas TEXT,
    data                    DATE NOT NULL,
    estado                  TEXT NOT NULL DEFAULT 'vigente' CHECK (estado IN ('vigente', 'superseded')),
    substitui               TEXT,
    superseded_by           TEXT,
    relacionadas            TEXT[] NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT decisions_org_codigo_unique UNIQUE (org_id, codigo)
);

ALTER TABLE academia_de_reciclagem.decisions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "decisions_select_own_org" ON academia_de_reciclagem.decisions;
CREATE POLICY "decisions_select_own_org" ON academia_de_reciclagem.decisions
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.decisions;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.decisions FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE TRIGGER set_updated_at_decisions
    BEFORE UPDATE ON academia_de_reciclagem.decisions
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_decisions_org ON academia_de_reciclagem.decisions(org_id);
CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_decisions_estado ON academia_de_reciclagem.decisions(org_id, estado);

-- Append-only guard. Runs BEFORE the `set_updated_at` trigger fires on the
-- SAME statement — Postgres executes same-timing triggers in name order,
-- and `academia_decisions_append_only` < `set_updated_at_decisions`
-- alphabetically, so this check sees the pre-touch OLD/NEW pair. `updated_at`
-- itself is deliberately exempt (the touch trigger must be allowed to move
-- it) alongside `estado` and `superseded_by`.
CREATE OR REPLACE FUNCTION academia_de_reciclagem.academia_decisions_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql SECURITY DEFINER SET search_path = academia_de_reciclagem, public
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'decisions is append-only: DELETE is not permitted (codigo=%)', OLD.codigo
            USING ERRCODE = '0A000';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.id IS DISTINCT FROM OLD.id
           OR NEW.org_id IS DISTINCT FROM OLD.org_id
           OR NEW.codigo IS DISTINCT FROM OLD.codigo
           OR NEW.titulo IS DISTINCT FROM OLD.titulo
           OR NEW.contexto IS DISTINCT FROM OLD.contexto
           OR NEW.decisao IS DISTINCT FROM OLD.decisao
           OR NEW.motivo IS DISTINCT FROM OLD.motivo
           OR NEW.alternativas_rejeitadas IS DISTINCT FROM OLD.alternativas_rejeitadas
           OR NEW.data IS DISTINCT FROM OLD.data
           OR NEW.substitui IS DISTINCT FROM OLD.substitui
           OR NEW.relacionadas IS DISTINCT FROM OLD.relacionadas
           OR NEW.created_at IS DISTINCT FROM OLD.created_at
        THEN
            RAISE EXCEPTION 'decisions is append-only: only estado and superseded_by may change (codigo=%)', OLD.codigo
                USING ERRCODE = '0A000';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER academia_decisions_append_only
    BEFORE UPDATE OR DELETE ON academia_de_reciclagem.decisions
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.academia_decisions_append_only();


-- ============================================================================
-- A.3 open_questions
-- ============================================================================

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.open_questions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           UUID NOT NULL,
    codigo           TEXT NOT NULL,
    pergunta         TEXT NOT NULL,
    por_que_importa  TEXT NOT NULL,
    bloqueia         TEXT NOT NULL,
    destino_kb       TEXT,
    estado           TEXT NOT NULL DEFAULT 'aberta' CHECK (estado IN ('aberta', 'respondida')),
    resposta         TEXT,
    respondida_em    TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT open_questions_org_codigo_unique UNIQUE (org_id, codigo)
);

ALTER TABLE academia_de_reciclagem.open_questions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "open_questions_select_own_org" ON academia_de_reciclagem.open_questions;
CREATE POLICY "open_questions_select_own_org" ON academia_de_reciclagem.open_questions
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.open_questions;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.open_questions FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE TRIGGER set_updated_at_open_questions
    BEFORE UPDATE ON academia_de_reciclagem.open_questions
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_open_questions_org ON academia_de_reciclagem.open_questions(org_id);
CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_open_questions_estado ON academia_de_reciclagem.open_questions(org_id, estado);


-- ============================================================================
-- A.4 roadmap_phases
-- ============================================================================

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.roadmap_phases (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL,
    codigo            TEXT NOT NULL,
    titulo            TEXT NOT NULL,
    objetivo          TEXT NOT NULL,
    concluida_quando  TEXT NOT NULL,
    estado            TEXT NOT NULL DEFAULT 'pendente' CHECK (estado IN ('pendente', 'em-andamento', 'concluida', 'cancelada')),
    ordem             INT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT roadmap_phases_org_codigo_unique UNIQUE (org_id, codigo)
);

ALTER TABLE academia_de_reciclagem.roadmap_phases ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "roadmap_phases_select_own_org" ON academia_de_reciclagem.roadmap_phases;
CREATE POLICY "roadmap_phases_select_own_org" ON academia_de_reciclagem.roadmap_phases
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.roadmap_phases;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.roadmap_phases FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE TRIGGER set_updated_at_roadmap_phases
    BEFORE UPDATE ON academia_de_reciclagem.roadmap_phases
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_roadmap_phases_org ON academia_de_reciclagem.roadmap_phases(org_id, ordem);


-- ============================================================================
-- A.5 tasks
-- ============================================================================

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.tasks (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    codigo         TEXT NOT NULL,
    titulo         TEXT NOT NULL,
    fase           TEXT NOT NULL,
    detalhe        TEXT,
    estado         TEXT NOT NULL DEFAULT 'pendente' CHECK (estado IN ('pendente', 'em-andamento', 'concluida', 'cancelada')),
    bloqueada_por  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tasks_org_codigo_unique UNIQUE (org_id, codigo)
);

ALTER TABLE academia_de_reciclagem.tasks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "tasks_select_own_org" ON academia_de_reciclagem.tasks;
CREATE POLICY "tasks_select_own_org" ON academia_de_reciclagem.tasks
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.tasks;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.tasks FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE TRIGGER set_updated_at_tasks
    BEFORE UPDATE ON academia_de_reciclagem.tasks
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_tasks_org ON academia_de_reciclagem.tasks(org_id);
CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_tasks_fase ON academia_de_reciclagem.tasks(org_id, fase);
CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_tasks_estado ON academia_de_reciclagem.tasks(org_id, estado);


-- ============================================================================
-- A.6 content_drafts
-- ============================================================================

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.content_drafts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    codigo      TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('roteiro', 'trilha', 'quiz', 'copy', 'proposta', 'outro')),
    titulo      TEXT NOT NULL,
    corpo_md    TEXT NOT NULL,
    referencia  TEXT,
    fontes      TEXT[] NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT content_drafts_org_codigo_unique UNIQUE (org_id, codigo)
);

ALTER TABLE academia_de_reciclagem.content_drafts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "content_drafts_select_own_org" ON academia_de_reciclagem.content_drafts;
CREATE POLICY "content_drafts_select_own_org" ON academia_de_reciclagem.content_drafts
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.content_drafts;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.content_drafts FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE TRIGGER set_updated_at_content_drafts
    BEFORE UPDATE ON academia_de_reciclagem.content_drafts
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_content_drafts_org ON academia_de_reciclagem.content_drafts(org_id);
CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_content_drafts_tipo ON academia_de_reciclagem.content_drafts(org_id, tipo);


-- ============================================================================
-- A.7 timeline_events — ordered by data DESC, created_at DESC
-- ============================================================================

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.timeline_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    data        DATE NOT NULL,
    titulo      TEXT NOT NULL,
    descricao   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE academia_de_reciclagem.timeline_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "timeline_events_select_own_org" ON academia_de_reciclagem.timeline_events;
CREATE POLICY "timeline_events_select_own_org" ON academia_de_reciclagem.timeline_events
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.timeline_events;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.timeline_events FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE TRIGGER set_updated_at_timeline_events
    BEFORE UPDATE ON academia_de_reciclagem.timeline_events
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_timeline_events_org_data ON academia_de_reciclagem.timeline_events(org_id, data DESC, created_at DESC);


-- ============================================================================
-- A.8 research_sources — kb_slug FKs to kb_entries(org_id, slug); 404
-- mapping for an unknown slug happens at the store level (an explicit
-- existence check before insert), not by translating a Postgres FK error —
-- the FK constraint here is a DB-level integrity backstop, not the
-- application's error-shaping path.
-- ============================================================================

CREATE TABLE IF NOT EXISTS academia_de_reciclagem.research_sources (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL,
    url                   TEXT NOT NULL,
    titulo                TEXT NOT NULL,
    trecho_citado         TEXT NOT NULL,
    resumo                TEXT NOT NULL,
    kb_slug               TEXT NOT NULL,
    vigencia_confirmada   BOOLEAN NOT NULL DEFAULT false,
    exige_da_empresa      TEXT,
    accessed_at           TIMESTAMPTZ NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT research_sources_kb_slug_fkey FOREIGN KEY (org_id, kb_slug)
        REFERENCES academia_de_reciclagem.kb_entries (org_id, slug)
);

ALTER TABLE academia_de_reciclagem.research_sources ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "research_sources_select_own_org" ON academia_de_reciclagem.research_sources;
CREATE POLICY "research_sources_select_own_org" ON academia_de_reciclagem.research_sources
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "service_role_bypass" ON academia_de_reciclagem.research_sources;
CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.research_sources FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE OR REPLACE TRIGGER set_updated_at_research_sources
    BEFORE UPDATE ON academia_de_reciclagem.research_sources
    FOR EACH ROW EXECUTE FUNCTION academia_de_reciclagem.set_updated_at();

CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_research_sources_org ON academia_de_reciclagem.research_sources(org_id);
CREATE INDEX IF NOT EXISTS idx_academia_de_reciclagem_research_sources_kb_slug ON academia_de_reciclagem.research_sources(org_id, kb_slug);
