-- ============================================================================
-- Migration 048 -- social_wiring: the person layer (`clientes`)
--
-- lead-card-hub Phase 1 (roadmap `project-history/roadmaps/lead-card-hub-2026-08.md`
-- §5 Phase 1; contract `products/social-wiring/projects/lead-card-hub-p1-PROJECT.md`
-- §4). Slice A of that contract: this file is DDL only. It creates the schema;
-- it does NOT populate a single row. Population is a Python operation
-- (`app/services/clientes_service.py::run_backfill`, `app/services/
-- identidade_service.py` for the resolution algorithm) run AFTER this file is
-- applied and AFTER the tech-lead has an explicit go-ahead from the user
-- (contract §7 -- there is no dev database; this runs against the single live
-- Supabase project while WhatsApp intake keeps writing to `leads`).
--
-- WHY THE BACKFILL IS NOT SQL IN THIS FILE, UNLIKE 037's PART B
-- ---------------------------------------------------------------
-- 037's phone-format backfill was one deterministic transform
-- (`normalize_phone(contato)`) safely expressible as a couple of `UPDATE`
-- statements. This backfill runs a multi-step matching algorithm (name
-- normalization, token-prefix compatibility, first-name-divergence
-- detection, cluster-to-cliente assignment) across ~13k+ rows, whose only
-- honest pre-apply verification is a unit-tested Python implementation
-- (`identidade_service.py`) -- there is no live database to test raw SQL
-- DO-block logic against, and getting a matching algorithm wrong via
-- untestable SQL is a much worse failure mode than via a covered Python
-- module. See `identidade_service.py`'s module docstring for the full C1-C6
-- predicate and `clientes_service.py::run_backfill` for the write path.
--
-- WHAT THIS FILE ITSELF DOES, AND WHY IT IS SAFE TO APPLY BEFORE THE BACKFILL
-- ------------------------------------------------------------------------
-- 1. Creates `clientes`, `cliente_touches`, `cliente_merges` -- new tables,
--    zero blast radius on anything that already runs.
-- 2. Adds `negociacoes_venda.cliente_id`, nullable, FK to the new `clientes`
--    table. Every existing row gets NULL here; nothing reads this column yet
--    (Slice B has not shipped), so a NULL cliente_id changes no behaviour.
-- 3. Drops `negociacoes_venda_exactly_one_origin`. This is INDEPENDENT of
--    `cliente_id` being populated -- the CHECK only ever asserted
--    `num_nonnulls(lead_id, meta_ads_lead_id) = 1`, which has nothing to do
--    with `cliente_id`. Dropping it is a pure widening (stops enforcing an
--    invariant, invalidates nothing already stored) and can happen the
--    moment this file applies, well before the backfill repoints a single
--    row. `lead_id`/`meta_ads_lead_id` are KEPT (contract §4: "dropping them
--    is lossy and not required by anything in Phase 1").
--
-- 🔴 THE 399 KEYLESS LEADS (contract §2)
-- ----------------------------------------
-- 399 `leads` rows have `contato_norm IS NULL` -- no phone, no email, no key
-- to resolve identity on. `clientes.chave_canonica` is therefore NULLABLE,
-- and `UNIQUE (org_id, chave_canonica)` below is a PARTIAL index
-- (`WHERE chave_canonica IS NOT NULL`), never a plain UNIQUE. A plain
-- UNIQUE constraint is satisfied by any number of NULLs (SQL nulls never
-- compare equal to each other), which LOOKS like the right guarantee and
-- silently permits a second REAL duplicate key later -- the exact defect
-- this migration exists to prevent, reintroduced by the naive version of
-- the fix. `identidade_incerta` flags a keyless cliente (or, see below, a
-- review-pending one) so the UI can distinguish "resolved" from "not".
--
-- 🔴 THE UNIQUE CONSTRAINT ALSO SHAPES HOW REVIEW GROUPS ARE STORED
-- ---------------------------------------------------------------------
-- At most ONE cliente may ever hold a given real `chave_canonica`. A group
-- the backfill sends to review (C4-C6 -- names that genuinely conflict,
-- e.g. the `+5511974781330` shared-household-phone case in the roadmap)
-- therefore CANNOT be represented as several clientes that all
-- provisionally claim that same phone -- that would violate this
-- constraint the moment the backfill runs, not eventually. Instead the
-- backfill creates one cliente per distinct candidate identity with
-- `chave_canonica = NULL, identidade_incerta = true` for ALL of them,
-- until a human resolves the ambiguity (Slice B's
-- `POST /api/clientes/revisao/{grupo}/merge`) and one of them claims the
-- key for real. Nothing is lost in the meantime: the real key survives on
-- every `cliente_touches.chave_canonica` row (see below) and, losslessly,
-- on the untouched source `leads`/`meta_ads_leads` row. This is a
-- generalisation of `identidade_incerta` beyond the contract §2 case it
-- was named for ("no key at all") to also cover "a real key that is
-- provably shared and therefore not safe to claim yet" -- surfaced
-- explicitly as an interpretation call in the Slice A delivery note, since
-- the contract does not spell this case out.
--
-- LOSSLESSNESS (contract §4 P1.2, D-something in the roadmap)
-- -------------------------------------------------------------
-- `cliente_touches` gets exactly one row per `leads` row and per
-- `meta_ads_leads` row -- no source row is ever modified or deleted by
-- this migration or its backfill. Verification is arithmetic:
-- `count(cliente_touches) == count(leads) + count(meta_ads_leads)`
-- (13 330 + 1 152 = 14 482 at the live count the contract was written
-- against; whatever the counts are when the backfill actually runs is
-- what the report asserts, per the backfill's own idempotency contract).
--
-- REVERSIBILITY (D3): `cliente_merges` MUST hold enough of the absorbed
-- identity to rebuild it without the row still existing -- because for an
-- AUTOMATIC merge (this backfill), no `clientes` row is ever inserted for
-- the losing name-cluster in the first place (creating one, even
-- transiently, would collide with the UNIQUE constraint above the instant
-- both clusters tried to hold the same key). `cliente_id_absorvido` is
-- therefore a stable synthetic handle for the folded identity, not
-- necessarily a formerly-real row id; `nome_absorvido` /
-- `chave_canonica_absorvido` / `chave_tipo_absorvido` /
-- `identidade_incerta_absorvido` are the snapshot that lets undo recreate
-- an equivalent cliente, and `touches_movidos` (JSONB -- genuinely
-- variable-length, unlike the fixed-shape snapshot columns, same
-- reasoning `meta_ads_leads.answers` uses for its variable tail) records
-- exactly which `(origem_tabela, origem_id)` touches to move back so the
-- split is a real, not approximate, reversal.
--
-- D17 -- negociacoes_venda IS ONE-TO-MANY FROM THE START: `cliente_id` has
-- no UNIQUE constraint. A cliente accumulates negociações over time and
-- closed ones stay as history (contract §4) -- building this as
-- effectively-one-to-one and widening it later is exactly what D17 rules
-- out.
--
-- FORWARD-ONLY, IDEMPOTENT (CREATE ... IF NOT EXISTS / DROP ... IF EXISTS),
-- matching every migration in this product. 🔴 MIGRATION FILE ONLY -- not
-- applied to any database by this change (contract §7). Apply via
-- `noctus.dev.migrate_product` only after the tech-lead has stated the row
-- counts this will touch and the user has given an explicit go-ahead.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. clientes -- P1.1
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.clientes (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                UUID NOT NULL,
    nome                  TEXT,
    -- E.164 phone or lowercased email -- NULLABLE, see the 399-keyless note
    -- above. NEVER re-derived here: always copied verbatim from
    -- `leads.contato_norm` / `meta_ads_leads.phone` / `.email`, which are
    -- themselves already canonical (migration 037's trigger).
    chave_canonica        TEXT,
    chave_tipo            TEXT CHECK (chave_tipo IN ('telefone', 'email')),
    -- True for: (a) the 399 keyless leads (no chave_canonica at all), and
    -- (b) every cliente in an unresolved review group (a real key exists
    -- somewhere but is shared/ambiguous -- see the review-groups note
    -- above). Never true with a chave_canonica also set -- see the CHECK.
    identidade_incerta    BOOLEAN NOT NULL DEFAULT false,
    ativo                 BOOLEAN NOT NULL DEFAULT true,
    inativo_em            TIMESTAMPTZ,
    arquivado_em          TIMESTAMPTZ,
    -- Derived from cliente_touches (MIN/MAX of ocorreu_em), maintained by
    -- the service layer on every touch write -- not a generated column,
    -- because a merge/undo moves touches between clientes and both sides'
    -- spans need recomputing at that moment, not just on INSERT.
    primeiro_contato_em   TIMESTAMPTZ,
    ultimo_contato_em     TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ,
    CONSTRAINT clientes_chave_tipo_matches_chave
        CHECK ((chave_canonica IS NULL) = (chave_tipo IS NULL)),
    CONSTRAINT clientes_incerta_implies_no_key
        CHECK (NOT identidade_incerta OR chave_canonica IS NULL)
);

-- 🔴 PARTIAL, not a plain UNIQUE -- see the header. A plain UNIQUE is
-- satisfied by all 399 nulls (and by every unresolved review-group cliente,
-- which ALSO holds chave_canonica = NULL) and would silently let a second
-- real duplicate key in later. This is the only correct form.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_clientes_org_chave
    ON social_wiring.clientes (org_id, chave_canonica)
    WHERE chave_canonica IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sw_clientes_org_ativo
    ON social_wiring.clientes (org_id, ativo);
CREATE INDEX IF NOT EXISTS idx_sw_clientes_org_incerta
    ON social_wiring.clientes (org_id, identidade_incerta) WHERE identidade_incerta;

ALTER TABLE social_wiring.clientes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "clientes_select_own_org" ON social_wiring.clientes;
CREATE POLICY "clientes_select_own_org" ON social_wiring.clientes
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "clientes_service_role" ON social_wiring.clientes;
CREATE POLICY "clientes_service_role" ON social_wiring.clientes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. cliente_touches -- P1.2, the lossless timeline substrate
-- ----------------------------------------------------------------------------
-- One row per `leads` row and per `meta_ads_leads` row, ALWAYS -- no source
-- row is modified or deleted by this migration or its backfill.
--
-- `origem_tabela` + `origem_id` (TEXT, not a typed FK) rather than two
-- nullable FK columns: mirrors `pipeline_movimentos.entidade_id`'s already-
-- established rationale in this file's own product (034 §4) -- one column
-- cannot reference two tables with different PK types (`leads.id` is UUID,
-- `meta_ads_leads.id` is Meta's own TEXT id), and the UNIQUE index below is
-- what makes the backfill idempotent, not a foreign key.
--
-- `nome` / `chave_canonica` / `origem_label` are denormalized on purpose:
-- `chave_canonica` in particular is what lets a review-pending cliente
-- (whose OWN chave_canonica is NULL, per the header) still be found by the
-- real key it shares with its siblings, with no join back to
-- `leads`/`meta_ads_leads` required.
CREATE TABLE IF NOT EXISTS social_wiring.cliente_touches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cliente_id      UUID NOT NULL REFERENCES social_wiring.clientes(id) ON DELETE CASCADE,
    org_id          UUID NOT NULL,
    origem_tabela   TEXT NOT NULL CHECK (origem_tabela IN ('leads', 'meta_ads_leads')),
    origem_id       TEXT NOT NULL,
    ocorreu_em      TIMESTAMPTZ NOT NULL,
    nome            TEXT,
    chave_canonica  TEXT,
    origem_label    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Re-running the backfill must never double-count a row -- this is the
-- idempotency guarantee, not a service-layer check. Deliberately NOT
-- scoped by org_id: `leads.id` is a UUID and `meta_ads_leads.id` is Meta's
-- own globally-unique lead id, so (origem_tabela, origem_id) alone is
-- already globally unique.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_cliente_touches_origem
    ON social_wiring.cliente_touches (origem_tabela, origem_id);
CREATE INDEX IF NOT EXISTS idx_sw_cliente_touches_cliente_ocorreu
    ON social_wiring.cliente_touches (cliente_id, ocorreu_em DESC);
-- Powers the review-group recovery join -- see the header.
CREATE INDEX IF NOT EXISTS idx_sw_cliente_touches_org_chave
    ON social_wiring.cliente_touches (org_id, chave_canonica);

ALTER TABLE social_wiring.cliente_touches ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_touches_select_own_org" ON social_wiring.cliente_touches;
CREATE POLICY "cliente_touches_select_own_org" ON social_wiring.cliente_touches
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_touches_service_role" ON social_wiring.cliente_touches;
CREATE POLICY "cliente_touches_service_role" ON social_wiring.cliente_touches
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. cliente_merges -- P1.3, D3 (undoable)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.cliente_merges (
    id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                        UUID NOT NULL,
    cliente_id_sobrevivente       UUID NOT NULL REFERENCES social_wiring.clientes(id),
    -- NOT a foreign key -- see the header. For an automatic merge (this
    -- backfill) no row was ever inserted for the losing identity; for a
    -- manual merge (Slice B) the row it names has been deleted by the
    -- merge itself. Either way this table, not a live `clientes` row, is
    -- the source of truth for undo.
    cliente_id_absorvido          UUID NOT NULL,
    motivo                        TEXT NOT NULL CHECK (motivo IN ('C1', 'C2', 'C3', 'C4', 'C5', 'C6')),
    automatico                    BOOLEAN NOT NULL DEFAULT true,
    nome_absorvido                TEXT,
    chave_canonica_absorvido      TEXT,
    chave_tipo_absorvido          TEXT,
    identidade_incerta_absorvido  BOOLEAN NOT NULL DEFAULT false,
    -- [{"origem_tabela": "leads", "origem_id": "..."}, ...] -- exactly which
    -- touches moved, so undo moves back exactly those and nothing else.
    -- JSONB because this is genuinely variable-length (one merge can fold
    -- 1 or dozens of touches), unlike the fixed-shape snapshot columns
    -- above -- same split `meta_ads_leads` uses between typed core columns
    -- and its variable `answers` tail.
    touches_movidos               JSONB NOT NULL DEFAULT '[]'::jsonb,
    desfeito_em                   TIMESTAMPTZ,
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN social_wiring.cliente_merges.cliente_id_absorvido IS
    'A stable handle for the folded identity, NOT necessarily a formerly-'
    'real clientes.id. For an automatic merge (the P1 backfill) no row was '
    'ever inserted for the losing name-cluster (would collide with '
    'uq_sw_clientes_org_chave the instant two clusters claimed one key). '
    'For a manual merge the id names a row that has since been deleted. '
    'Undo always recreates a NEW cliente from the snapshot columns on this '
    'row; it never expects this id to resolve.';

CREATE INDEX IF NOT EXISTS idx_sw_cliente_merges_sobrevivente
    ON social_wiring.cliente_merges (cliente_id_sobrevivente);
CREATE INDEX IF NOT EXISTS idx_sw_cliente_merges_org_pending
    ON social_wiring.cliente_merges (org_id) WHERE desfeito_em IS NULL;

ALTER TABLE social_wiring.cliente_merges ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cliente_merges_select_own_org" ON social_wiring.cliente_merges;
CREATE POLICY "cliente_merges_select_own_org" ON social_wiring.cliente_merges
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "cliente_merges_service_role" ON social_wiring.cliente_merges;
CREATE POLICY "cliente_merges_service_role" ON social_wiring.cliente_merges
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 4. negociacoes_venda -- P1.4, the repoint
-- ----------------------------------------------------------------------------
-- Nullable + ON DELETE SET NULL: a negociação (a sale, a real business
-- record) must survive even a cliente being deleted (e.g. an undo edge
-- case) -- it becomes identity-orphaned, not gone. The "zero NULL
-- cliente_id" invariant (contract §4) is asserted by the BACKFILL's own
-- report immediately after it runs, not enforced permanently at the DB
-- level, precisely because SET NULL can legitimately reintroduce one later.
ALTER TABLE social_wiring.negociacoes_venda
    ADD COLUMN IF NOT EXISTS cliente_id UUID
        REFERENCES social_wiring.clientes(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_sw_negociacoes_venda_cliente
    ON social_wiring.negociacoes_venda (cliente_id);

-- Independent of cliente_id being populated -- see the header's point 3.
-- `lead_id` / `meta_ads_lead_id` are KEPT (contract §4: dropping them is
-- lossy and nothing in Phase 1 needs it).
ALTER TABLE social_wiring.negociacoes_venda
    DROP CONSTRAINT IF EXISTS negociacoes_venda_exactly_one_origin;

NOTIFY pgrst, 'reload schema';
