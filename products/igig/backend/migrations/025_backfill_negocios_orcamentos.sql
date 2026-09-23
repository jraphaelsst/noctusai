-- ============================================================================
-- IgIg — backfill: pre-funnel leads/orçamentos get their Comercial cards
-- (tech-lead addendum to wave-2, found in the live DB after 016–024).
--
-- The Comercial funnel (migrations 017/018) launched AFTER leads and
-- orçamentos already existed in production. A lead created before the funnel
-- shipped has no `negocio` row, so it is INVISIBLE on the board (the board is
-- `negocio`-keyed, never `lead`-keyed) — and a pre-funnel orçamento has no
-- `negocio_id`, so it cannot be found from a card even once one exists.
--
-- Every statement here is idempotent and ORG-SCOPED by construction:
--   * stage seeding    — `ON CONFLICT (org_id, pipeline, slug) DO NOTHING`,
--                        the exact guard `app/pipelines.py::garantir_etapas_padrao`
--                        uses at runtime (same VALUES as `COMERCIAL_PADRAO`,
--                        pinned by `tests/test_pipelines.py::
--                        test_migration_025_seeds_exactly_the_python_comercial_defaults`).
--   * negócio backfill — `WHERE NOT EXISTS (... negocio WHERE lead_id = l.id)`,
--                        so a lead that already has a card (funnel-era or a
--                        prior run of this file) is never touched twice.
--   * orçamento link   — `WHERE o.negocio_id IS NULL`, so an orçamento
--                        already linked (funnel-era or a prior run) is left
--                        alone.
-- Re-running this file is therefore a no-op past the first successful run —
-- required because `migrate_product` only replays PENDING files, but a
-- partial/retried apply must still converge, the same contract every other
-- igig migration in this set carries.
--
-- No new table/column — `NNN_igig_*.sql`'s SQLite-parity requirement
-- (`tests/test_schema_parity.py::test_every_pg_domain_migration_has_a_sqlite_counterpart`)
-- only binds files matching that glob; this one is named WITHOUT `_igig_`
-- (precedent: 013/014/016/019/024, also non-table-declaring), so it carries
-- no SQLite mirror — there is nothing for `aplicar_schema_sqlite` to mirror.
--
-- No new trigger/CHECK/UNIQUE guard is declared here (pure backfill DML), so
-- no `noctus.dev.verify_db_guards` probe applies (that tool proves a
-- DECLARED guard's refusal; there is none to prove).
-- ============================================================================
SET search_path = igig, public;

-- ----------------------------------------------------------------------------
-- (a) Comercial default stages for every org that has a lead but never
--     opened the funnel (so it never lazily seeded via `garantir_etapas_padrao`).
--     Slugs/labels/cores/posições/papel are IDENTICAL to `COMERCIAL_PADRAO`
--     (`app/pipelines.py`) — an org that already seeded (funnel-era) or
--     customised its stages is untouched by the unique-key conflict.
-- ----------------------------------------------------------------------------
INSERT INTO igig.pipeline_stages (org_id, pipeline, slug, label, cor, posicao, papel)
SELECT o.org_id, 'comercial', v.slug, v.label, v.cor, v.posicao, v.papel
  FROM (SELECT DISTINCT org_id FROM igig.lead) AS o
 CROSS JOIN (VALUES
    ('leads',            'Leads',            'primary',   0, NULL),
    ('qualificacao',     'Qualificação',     'secondary', 1, NULL),
    ('negociacao',       'Negociação',       'warning',   2, NULL),
    ('agendar_briefing', 'Agendar briefing', 'muted',     3, NULL),
    ('fechado',          'Fechado',          'success',   4, 'fechado')
 ) AS v (slug, label, cor, posicao, papel)
ON CONFLICT (org_id, pipeline, slug) DO NOTHING;

-- ----------------------------------------------------------------------------
-- (b1) A negócio for every OPEN lead (novo|qualificado) with none yet — lands
--      in the entry stage (lowest `posicao`, active), exactly where
--      `abrir_negocio` puts a fresh card. `kanban_pos` is spaced by
--      creation order so the column renders in a stable, sensible sequence
--      the first time it is opened (a drag immediately after re-orders it
--      for real, the same as any other card).
-- ----------------------------------------------------------------------------
INSERT INTO igig.negocio (org_id, lead_id, titulo, etapa_id, kanban_pos, status)
SELECT
    l.org_id, l.id,
    COALESCE(NULLIF(trim(l.empresa), ''), NULLIF(trim(l.nome), ''), 'Negócio'),
    (
        SELECT s.id FROM igig.pipeline_stages AS s
         WHERE s.org_id = l.org_id AND s.pipeline = 'comercial' AND s.ativo = TRUE
         ORDER BY s.posicao ASC
         LIMIT 1
    ),
    row_number() OVER (PARTITION BY l.org_id ORDER BY l.created_at),
    'aberto'
  FROM igig.lead AS l
 WHERE l.status IN ('novo', 'qualificado')
   AND NOT EXISTS (SELECT 1 FROM igig.negocio AS n WHERE n.lead_id = l.id);

-- ----------------------------------------------------------------------------
-- (b2) A GANHO negócio, in Fechado, for every CONVERTIDO lead that already
--      has a cliente — the deal it closed pre-funnel, made visible on the
--      board's Fechado column. `ganho_em` best-effort dates the win to when
--      the lead record last changed (its conversion), never a bare `now()`
--      that would misreport a years-old win as happening today.
-- ----------------------------------------------------------------------------
INSERT INTO igig.negocio (org_id, lead_id, titulo, etapa_id, kanban_pos, status, ganho_em, cliente_id)
SELECT
    l.org_id, l.id,
    COALESCE(NULLIF(trim(l.empresa), ''), NULLIF(trim(l.nome), ''), 'Negócio'),
    (
        SELECT s.id FROM igig.pipeline_stages AS s
         WHERE s.org_id = l.org_id AND s.pipeline = 'comercial' AND s.papel = 'fechado'
         LIMIT 1
    ),
    row_number() OVER (PARTITION BY l.org_id ORDER BY l.created_at),
    'ganho',
    COALESCE(l.updated_at, l.created_at, now()),
    l.cliente_id
  FROM igig.lead AS l
 WHERE l.status = 'convertido'
   AND l.cliente_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM igig.negocio AS n WHERE n.lead_id = l.id);

-- The cliente this deal closed didn't necessarily carry `negocio_id` back
-- (that column only exists since 018 and only ever WRITTEN by
-- `_garantir_cliente` on a LIVE close) — backfill it now that the negócio
-- exists, exactly the field it would have carried had it closed post-funnel.
UPDATE igig.cliente AS c
   SET negocio_id = n.id
  FROM igig.negocio AS n
 WHERE n.cliente_id = c.id
   AND n.status = 'ganho'
   AND c.negocio_id IS NULL;

-- ----------------------------------------------------------------------------
-- (c) Legacy orçamentos (created before `orcamento.negocio_id` existed, or by
--     the removed `/api/comercial/orcamentos*` endpoints) → their lead's
--     negócio, found directly by `lead_id` or, for the older shape that only
--     ever carried `cliente_id`, through `cliente.lead_id`. `versao` is
--     RESEQUENCED (not merely defaulted) for every orçamento this backfill
--     links to the same negócio, oldest first — a legacy row's `versao` was
--     never meaningful against orçamentos of OTHER leads it is only now being
--     grouped with, and leaving duplicates would violate
--     `idx_igig_orcamento_versao` the moment two of them shared a negócio.
--     A genuine data conflict this cannot resolve on its own (two ALREADY
--     `aceito` orçamentos landing on the same negócio) fails LOUDLY against
--     `idx_igig_orcamento_um_aceito` rather than silently picking a winner —
--     the same no-silent-errors posture `test_migration_017` [sic 017's own
--     `DO $$ ... RAISE EXCEPTION` verification block] uses for its backfill.
-- ----------------------------------------------------------------------------
WITH alvo AS (
    SELECT o.id AS orcamento_id, n.id AS negocio_id,
           row_number() OVER (PARTITION BY n.id ORDER BY o.created_at, o.id) AS versao_nova
      FROM igig.orcamento AS o
      JOIN igig.negocio AS n
        ON n.org_id = o.org_id
       AND n.lead_id = COALESCE(
               o.lead_id,
               (SELECT c.lead_id FROM igig.cliente AS c
                 WHERE c.id = o.cliente_id AND c.org_id = o.org_id)
           )
     WHERE o.negocio_id IS NULL
)
UPDATE igig.orcamento AS o
   SET negocio_id = alvo.negocio_id,
       versao = alvo.versao_nova
  FROM alvo
 WHERE o.id = alvo.orcamento_id;
