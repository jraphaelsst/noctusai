-- ============================================================================
-- Migration 053 -- social_wiring: the card's core data surface (lead-card-hub
-- Phase 2, contract `products/social-wiring/projects/lead-card-hub-p2-PROJECT.md`
-- §2 "053 -- core card surface").
--
-- Adds the tables the card's detail dialog needs beyond what Phase 1 (048,
-- 049, 050) already shipped: annotations, one tag system (D6), assignment,
-- Trello-style dates + a reminder mechanism that exists nowhere in the
-- product today, and both checklist kinds (D11). Documents (055) are a
-- separate file -- LGPD-complete storage is its own migration per ruling S2.
--
-- Every table: `org_id uuid not null`, RLS enabled with the SAME
-- `current_org_id()` predicate 048/011 already established, plus a
-- service_role ALL policy -- this product's backend always reads/writes
-- through the service-role admin client (see `clientes_router.py`'s
-- `get_clientes_client()`), so the authenticated-SELECT policy is
-- defense-in-depth, not the live path, mirroring every prior migration in
-- this schema. `created_at timestamptz not null default now()` on every
-- table per the contract.
--
-- FORWARD-ONLY, IDEMPOTENT (CREATE ... IF NOT EXISTS / ADD COLUMN IF NOT
-- EXISTS / DROP POLICY IF EXISTS before CREATE POLICY), matching every
-- migration in this product. 🔴 MIGRATION FILE ONLY -- not applied to any
-- database by this change. Apply via `noctus.dev.migrate_product` only
-- after the tech-lead has an explicit go-ahead.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. cliente_notas -- Trello "Descrição" + "Comentários" (free-form)
-- ----------------------------------------------------------------------------
-- Soft-delete only (contract §2): a deleted note leaves a tombstone in the
-- timeline rather than rewriting history. `editado_em` is set by the PATCH
-- route on every edit -- NULL means "never edited", not "edited at
-- creation time".
--
-- 🔴 CONTRACT CORRECTION (post-053-authoring, surfaced by the frontend
-- engineer building against the same document): the contract originally
-- gave `cliente_notas` a single undifferentiated `corpo`, but the
-- screenshots show Descrição (one per card, editable in place, top of the
-- left pane) and Comentários (many, chronological, right-hand activity
-- pane) as distinct concepts -- conflating them forced the frontend to
-- guess ("oldest loaded nota = description"), which breaks the moment a
-- card's history exceeds one page. `tipo` is the discriminator; the
-- partial unique index below enforces "at most one descricao per
-- cliente" as a DB constraint, not an application-level promise.
CREATE TABLE IF NOT EXISTS social_wiring.cliente_notas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    cliente_id  UUID NOT NULL REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    autor_id    UUID,
    tipo        TEXT NOT NULL DEFAULT 'comentario' CHECK (tipo IN ('descricao', 'comentario')),
    corpo       TEXT NOT NULL,
    editado_em  TIMESTAMPTZ,
    deleted_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_cliente_notas_cliente
    ON social_wiring.cliente_notas (cliente_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sw_cliente_notas_org
    ON social_wiring.cliente_notas (org_id);
-- "At most one descricao per cliente" -- a DB constraint, not an
-- application-level promise. A soft-deleted descricao does not count
-- (its tombstone must not block creating a fresh one).
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_cliente_notas_one_descricao
    ON social_wiring.cliente_notas (cliente_id)
    WHERE tipo = 'descricao' AND deleted_at IS NULL;

ALTER TABLE social_wiring.cliente_notas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_notas_select_own_org" ON social_wiring.cliente_notas;
CREATE POLICY "cliente_notas_select_own_org" ON social_wiring.cliente_notas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_notas_service_role" ON social_wiring.cliente_notas;
CREATE POLICY "cliente_notas_service_role" ON social_wiring.cliente_notas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. cliente_tags + cliente_tag_links -- D6, ONE tag system
-- ----------------------------------------------------------------------------
-- `UNIQUE (org_id, lower(nome))` -- case-insensitive uniqueness within an
-- org's catalogue, matching the `uq_sw_clientes_org_chave` partial-index
-- shape of comparing on a normalized expression rather than the raw column.
CREATE TABLE IF NOT EXISTS social_wiring.cliente_tags (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    nome        TEXT NOT NULL,
    -- Hex colour, `#rrggbb`. A DB-level backstop for the primary Pydantic
    -- validation at the HTTP boundary -- never the only line of defense.
    cor         TEXT NOT NULL CHECK (cor ~ '^#[0-9a-fA-F]{6}$'),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_cliente_tags_org_nome
    ON social_wiring.cliente_tags (org_id, lower(nome));

ALTER TABLE social_wiring.cliente_tags ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_tags_select_own_org" ON social_wiring.cliente_tags;
CREATE POLICY "cliente_tags_select_own_org" ON social_wiring.cliente_tags
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_tags_service_role" ON social_wiring.cliente_tags;
CREATE POLICY "cliente_tags_service_role" ON social_wiring.cliente_tags
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE IF NOT EXISTS social_wiring.cliente_tag_links (
    cliente_id  UUID NOT NULL REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    tag_id      UUID NOT NULL REFERENCES social_wiring.cliente_tags(id) ON DELETE CASCADE,
    org_id      UUID NOT NULL,
    criado_por  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cliente_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_sw_cliente_tag_links_tag
    ON social_wiring.cliente_tag_links (tag_id);
CREATE INDEX IF NOT EXISTS idx_sw_cliente_tag_links_org
    ON social_wiring.cliente_tag_links (org_id);

ALTER TABLE social_wiring.cliente_tag_links ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_tag_links_select_own_org" ON social_wiring.cliente_tag_links;
CREATE POLICY "cliente_tag_links_select_own_org" ON social_wiring.cliente_tag_links
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_tag_links_service_role" ON social_wiring.cliente_tag_links;
CREATE POLICY "cliente_tag_links_service_role" ON social_wiring.cliente_tag_links
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. cliente_membros -- Trello "Membros" (assignment)
-- ----------------------------------------------------------------------------
-- Points at `lead_corretores.id`, NEVER at a name (contract §2) -- D10 adds
-- `user_id` there in Phase 3 and this table must not need changing when it
-- does.
CREATE TABLE IF NOT EXISTS social_wiring.cliente_membros (
    cliente_id        UUID NOT NULL REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    lead_corretor_id  UUID NOT NULL REFERENCES social_wiring.lead_corretores(id) ON DELETE CASCADE,
    org_id            UUID NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (cliente_id, lead_corretor_id)
);

CREATE INDEX IF NOT EXISTS idx_sw_cliente_membros_corretor
    ON social_wiring.cliente_membros (lead_corretor_id);
CREATE INDEX IF NOT EXISTS idx_sw_cliente_membros_org
    ON social_wiring.cliente_membros (org_id);

ALTER TABLE social_wiring.cliente_membros ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_membros_select_own_org" ON social_wiring.cliente_membros;
CREATE POLICY "cliente_membros_select_own_org" ON social_wiring.cliente_membros
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_membros_service_role" ON social_wiring.cliente_membros;
CREATE POLICY "cliente_membros_service_role" ON social_wiring.cliente_membros
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 4. clientes -- Trello "Datas" columns (screenshot 06)
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.clientes
    ADD COLUMN IF NOT EXISTS data_inicio             TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS data_entrega             TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS entrega_concluida        BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS lembrete_minutos_antes   INTEGER,
    ADD COLUMN IF NOT EXISTS recorrencia              TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'clientes_recorrencia_valid'
    ) THEN
        ALTER TABLE social_wiring.clientes
            ADD CONSTRAINT clientes_recorrencia_valid
            CHECK (recorrencia IS NULL OR recorrencia IN ('diaria', 'semanal', 'mensal', 'anual'));
    END IF;
END $$;

-- ----------------------------------------------------------------------------
-- 5. cliente_lembretes -- the reminder mechanism (exists nowhere today)
-- ----------------------------------------------------------------------------
-- One row represents one scheduled reminder fire. `destinatarios` is a
-- JSONB list (free-form today -- Phase 3/D10 will type this against real
-- noc users once corretores become invitable). The partial index is the
-- sweep's read path (contract §2): "which reminders still need to fire".
CREATE TABLE IF NOT EXISTS social_wiring.cliente_lembretes (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    cliente_id    UUID NOT NULL REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    dispara_em    TIMESTAMPTZ NOT NULL,
    enviado_em    TIMESTAMPTZ,
    cancelado_em  TIMESTAMPTZ,
    destinatarios JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_cliente_lembretes_pending
    ON social_wiring.cliente_lembretes (dispara_em)
    WHERE enviado_em IS NULL AND cancelado_em IS NULL;
CREATE INDEX IF NOT EXISTS idx_sw_cliente_lembretes_cliente
    ON social_wiring.cliente_lembretes (cliente_id, created_at DESC);

ALTER TABLE social_wiring.cliente_lembretes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_lembretes_select_own_org" ON social_wiring.cliente_lembretes;
CREATE POLICY "cliente_lembretes_select_own_org" ON social_wiring.cliente_lembretes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_lembretes_service_role" ON social_wiring.cliente_lembretes;
CREATE POLICY "cliente_lembretes_service_role" ON social_wiring.cliente_lembretes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 6. cliente_checklists + cliente_checklist_itens -- D11, both halves
-- ----------------------------------------------------------------------------
-- `origem='etapa'` is a stage-required checklist instantiated onto the
-- card; `'ad_hoc'` is user-created. `etapa_id` references
-- `pipeline_stages` (nullable, `ON DELETE SET NULL` -- a stage being
-- removed from the funil later must not cascade-delete a checklist that
-- already lives on a card; the card keeps its history). Multiple
-- checklists per card is required (screenshot 10) -- there is no
-- uniqueness constraint on `(cliente_id, titulo)`.
CREATE TABLE IF NOT EXISTS social_wiring.cliente_checklists (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,
    cliente_id  UUID NOT NULL REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    titulo      TEXT NOT NULL,
    posicao     INTEGER NOT NULL DEFAULT 0,
    origem      TEXT NOT NULL CHECK (origem IN ('ad_hoc', 'etapa')),
    etapa_id    UUID REFERENCES social_wiring.pipeline_stages(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_cliente_checklists_cliente
    ON social_wiring.cliente_checklists (cliente_id, posicao);

ALTER TABLE social_wiring.cliente_checklists ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_checklists_select_own_org" ON social_wiring.cliente_checklists;
CREATE POLICY "cliente_checklists_select_own_org" ON social_wiring.cliente_checklists
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_checklists_service_role" ON social_wiring.cliente_checklists;
CREATE POLICY "cliente_checklists_service_role" ON social_wiring.cliente_checklists
    FOR ALL TO service_role USING (true) WITH CHECK (true);

CREATE TABLE IF NOT EXISTS social_wiring.cliente_checklist_itens (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL,
    checklist_id   UUID NOT NULL REFERENCES social_wiring.cliente_checklists(id) ON DELETE CASCADE,
    texto          TEXT NOT NULL,
    concluido      BOOLEAN NOT NULL DEFAULT false,
    concluido_em   TIMESTAMPTZ,
    concluido_por  UUID,
    posicao        INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_cliente_checklist_itens_checklist
    ON social_wiring.cliente_checklist_itens (checklist_id, posicao);

ALTER TABLE social_wiring.cliente_checklist_itens ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_checklist_itens_select_own_org" ON social_wiring.cliente_checklist_itens;
CREATE POLICY "cliente_checklist_itens_select_own_org" ON social_wiring.cliente_checklist_itens
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_checklist_itens_service_role" ON social_wiring.cliente_checklist_itens;
CREATE POLICY "cliente_checklist_itens_service_role" ON social_wiring.cliente_checklist_itens
    FOR ALL TO service_role USING (true) WITH CHECK (true);
