-- ============================================================================
-- Migration 082 · social_wiring: roteiros + visitas — the qualificação → visita
-- funnel gets a real object.
--
-- WHAT WAS WRONG
-- --------------
-- The card could express a visit only as an AGENDAMENTO whose `tipo` happened
-- to be 'visita' (migration 061). That is a calendar entry, and a calendar
-- entry cannot be a route: it holds one property, it has no order, it cannot
-- be printed, and — the reason this migration exists — it cannot be COUNTED.
-- A corretor plans "first this one, then that one, last this one" and
-- afterwards has to record which visits actually happened. None of that fits
-- a `quando` and a `nota`.
--
-- So: `roteiros` (the route) and `visitas` (one property on it, with its
-- outcome). The Agendar button stops OFFERING 'visita' in the same commit —
-- but the CHECK on `atendimento_agendamentos.tipo` is NOT narrowed here, and
-- deliberately: live rows carry that value, and a migration that rejects data
-- which already exists is not a cutover, it is a break.
--
-- ── 🔴 WHOSE ROTEIRO IS IT — THE ATENDIMENTO'S ─────────────────────────
-- Migration 061's ruling, applied unchanged. A person accumulates deals over
-- time (D17) and closed ones stay as history, so a route walked for a 2024
-- purchase must not pile onto a live negotiation's list. The card is the
-- person and reads across all of their atendimentos, exactly as it already
-- does for agendamentos. Hanging roteiros off the person instead would give
-- the card two different ownership models for two adjacent tabs — and it is
-- also what keeps "what happened with this cliente in 2024" answerable PER
-- DEAL rather than as one undifferentiated pile.
--
-- ── 🔴 WHY `visitas` FKs TO THE REGISTRY AND NOT TO `imoveis` ──────────
-- The requirement behind this table is durability: per-imóvel statistics, and
-- a cliente history readable years later, so an agent handling this person in
-- 2028 knows what happened in 2024 — for sales triggers, and for caution.
--
-- That requirement RULES THE MIRROR OUT rather than pointing at it.
--
-- `social_wiring.imoveis` is a cache (040: "MIRROR of the Vista catalog"), and
-- Vista's /imoveis/listar returns only ACTIVE listings. Measured on prod
-- 2026-08-25 (migration 076's header): `imovel_registry` holds 3017 imóveis
-- and 1062 of them — 35% — are no longer in the 2008-row mirror.
--
--   1. A FK to `imoveis` would REJECT a third of the catalog at INSERT, and
--      the third it rejects is the wrong one: an imóvel leaves the catalog
--      when it is SOLD, which is exactly when its visit history matters most.
--   2. It would then DESTROY the history this table exists to keep. On delist,
--      ON DELETE CASCADE deletes our visitas; ON DELETE RESTRICT breaks the
--      nightly sync. Either way the 2024→2028 memory is gone, or the sync is.
--
-- Migration 063 settled this in one sentence — "`imovel_registry` — one row
-- per código we have EVER seen. APPEND-ONLY. Everything of ours joins HERE,
-- never to the mirror" — and migration 076 re-ratified it by moving
-- `imovel_dados` off the mirror for these same two reasons. This table copies
-- 076's shape verbatim: composite (org_id, codigo) → (org_id,
-- codigo_canonical), ON DELETE CASCADE, service-side `.upper()`.
--
-- The cascade is a statement about referential integrity, not a live deletion
-- path: the registry is append-only by design.
--
-- ── WHY `status` HAS THREE VALUES AND NOT A BOOLEAN ────────────────────
-- "Hasn't happened yet" and "didn't happen" are different facts. A boolean
-- merges them, and the count the user actually asked for — visitas that
-- happened vs. visitas that did not — would silently file every future visit
-- under "did not".
--
-- PREREQUISITE: 060 (atendimentos), 061 (the agendamentos precedent this
--               mirrors), 062 (the canonical código expression), 063
--               (imovel_registry), 075/076 (imovel_dados + the registry FK
--               shape), 080 (the security_invoker view posture).
-- FORWARD-ONLY, IDEMPOTENT.
--
-- 🔴 MIGRATION FILE ONLY — not applied to any DB by this change. Apply via
-- noctus.dev.migrate_product after the tech-lead states the row counts and the
-- user gives an explicit go-ahead.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. roteiros — one planned route, belonging to an atendimento
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.roteiros (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,

    -- ON DELETE CASCADE, same as `atendimento_agendamentos`: a route for a
    -- deal that no longer exists is not history, it is a dangling row that
    -- surfaces on no card and is swept by nothing.
    atendimento_id  UUID NOT NULL
        REFERENCES social_wiring.atendimentos(id) ON DELETE CASCADE,

    -- Optional. The UI falls back to the creation date, which is how a
    -- corretor refers to a route anyway ("o roteiro de terça").
    titulo          TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Soft delete, per D3's reversibility bar — the same bar that made the
    -- negociação collapse mark `substituida_por` instead of deleting, and that
    -- 061 applied to agendamentos.
    --
    -- No `updated_at` and no `status`: every card_hub table (056/057/061)
    -- carries `created_at` alone, and a roteiro's state is DERIVABLE from its
    -- visitas. A second, hand-maintained copy of it is how the two drift.
    deleted_at      TIMESTAMPTZ
);

ALTER TABLE social_wiring.roteiros ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "roteiros_select_own_org" ON social_wiring.roteiros;
CREATE POLICY "roteiros_select_own_org" ON social_wiring.roteiros
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "roteiros_service_role" ON social_wiring.roteiros;
CREATE POLICY "roteiros_service_role" ON social_wiring.roteiros
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- The card's read is "every live roteiro for these atendimentos, newest first".
CREATE INDEX IF NOT EXISTS idx_sw_roteiros_org_atendimento
    ON social_wiring.roteiros (org_id, atendimento_id, created_at DESC)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE social_wiring.roteiros IS
    'A planned visiting route, owned by an ATENDIMENTO (migration 061 ruling). '
    'Its visitas carry the order and the outcomes.';

-- ----------------------------------------------------------------------------
-- 2. visitas — one property on a route, and what happened there
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.visitas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL,

    roteiro_id  UUID NOT NULL
        REFERENCES social_wiring.roteiros(id) ON DELETE CASCADE,

    -- The CANONICAL código — `upper(btrim(...))`, migration 062's one
    -- expression for this schema. Stored already-canonical, normalised by the
    -- service on the way in, exactly as `imovel_dados` does after 076; a
    -- generated column here would be a SECOND normalisation to keep in step
    -- with the first. 076 verified on prod that `imovel_registry
    -- .codigo_canonical` and `imoveis.codigo` are both already uppercase
    -- everywhere (0 exceptions), so this needs no re-keying.
    codigo      TEXT NOT NULL,

    -- The visiting order the corretor dragged into place. 0-based.
    --
    -- Plain INTEGER with NO UNIQUE constraint, matching `checklists.posicao`
    -- in this module: a UNIQUE would force a DEFERRABLE constraint or a
    -- two-phase rewrite on every single drag. Ties break on `created_at`.
    ordem       INTEGER NOT NULL,

    -- 🔴 THE CONTABILIZAÇÃO. Three values, not a boolean — see the header.
    status      TEXT NOT NULL DEFAULT 'pendente',

    -- The corretor's feedback. Free text on purpose: this is the caution flag
    -- or the sales trigger someone reads back years later, and a fixed
    -- vocabulary would throw away the sentence that actually mattered.
    observacao  TEXT,

    -- Stamped when `status` FIRST leaves 'pendente', never re-stamped. It is
    -- the honest "when did this happen" the timeline derives its entry from —
    -- and following `timeline_service._gather_sistema`'s ruling on "restored",
    -- an event with no honestly derivable timestamp is omitted rather than
    -- stamped with now().
    feedback_em TIMESTAMPTZ,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ,

    CONSTRAINT visitas_status_valido
        CHECK (status IN ('pendente', 'realizada', 'nao_realizada')),

    -- 🔴 The registry FK — see the header. Composite key + CASCADE copied from
    -- `imovel_dados_registry_fk` (migration 076).
    CONSTRAINT visitas_registry_fk
        FOREIGN KEY (org_id, codigo)
        REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical)
        ON DELETE CASCADE
);

ALTER TABLE social_wiring.visitas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "visitas_select_own_org" ON social_wiring.visitas;
CREATE POLICY "visitas_select_own_org" ON social_wiring.visitas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "visitas_service_role" ON social_wiring.visitas;
CREATE POLICY "visitas_service_role" ON social_wiring.visitas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Reading one roteiro, in visiting order.
CREATE INDEX IF NOT EXISTS idx_sw_visitas_org_roteiro_ordem
    ON social_wiring.visitas (org_id, roteiro_id, ordem)
    WHERE deleted_at IS NULL;

-- "How many happened / didn't" across the org.
CREATE INDEX IF NOT EXISTS idx_sw_visitas_org_status
    ON social_wiring.visitas (org_id, status)
    WHERE deleted_at IS NULL;

-- "Everything that ever happened at ONE4770" — the per-imóvel history read.
CREATE INDEX IF NOT EXISTS idx_sw_visitas_org_codigo
    ON social_wiring.visitas (org_id, codigo)
    WHERE deleted_at IS NULL;

COMMENT ON TABLE social_wiring.visitas IS
    'One property on a roteiro, plus its outcome. Joins to imovel_registry '
    '(append-only), NEVER to the imoveis mirror — see the migration header: '
    '35% of registered imoveis have already left the catalog.';

-- ----------------------------------------------------------------------------
-- 3. vw_imovel_visita_contagem — the per-imóvel statistics surface
-- ----------------------------------------------------------------------------
-- Grouping lives in the database because PostgREST cannot GROUP BY, and the
-- alternative is the N+1 migration 080 had to undo: 29 brokers became 30
-- sequential round trips and made the slowest endpoint in production. Written
-- WITH the tables rather than after the loop is discovered.
--
-- `security_invoker = true` — the house default (071, 080). A definer-rights
-- view over an RLS'd table is a quiet way to read another org's counts.
--
-- Grouped on `codigo`, which is the REGISTRY key: a sold imóvel keeps its
-- counts forever. That is the entire point of the FK above.
--
-- Soft-deleted on EITHER side is excluded: a route someone removed did not
-- happen, and counting its visitas would inflate exactly the number this view
-- exists to report honestly.
CREATE OR REPLACE VIEW social_wiring.vw_imovel_visita_contagem
WITH (security_invoker = true)
AS
SELECT
    v.org_id,
    v.codigo,
    COUNT(*)                                           AS total,
    COUNT(*) FILTER (WHERE v.status = 'realizada')     AS realizadas,
    COUNT(*) FILTER (WHERE v.status = 'nao_realizada') AS nao_realizadas,
    COUNT(*) FILTER (WHERE v.status = 'pendente')      AS pendentes,
    COUNT(DISTINCT a.cliente_id)                       AS clientes_distintos,
    MIN(v.created_at)                                  AS primeira_visita_em,
    MAX(COALESCE(v.feedback_em, v.created_at))         AS ultima_visita_em
FROM social_wiring.visitas v
JOIN social_wiring.roteiros r
      ON r.id     = v.roteiro_id
     AND r.org_id = v.org_id
JOIN social_wiring.atendimentos a
      ON a.id     = r.atendimento_id
     AND a.org_id = r.org_id
WHERE v.deleted_at IS NULL
  AND r.deleted_at IS NULL
GROUP BY v.org_id, v.codigo;

COMMENT ON VIEW social_wiring.vw_imovel_visita_contagem IS
    'Visit counts per imovel, one row per (org_id, codigo) ever visited. '
    'Keyed on the registry codigo, so a delisted imovel keeps its history.';
