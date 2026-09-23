-- ============================================================================
-- Migration 161 · social_wiring: certidão soft-delete + audit trail (S3)
--
-- WHAT
-- ----
-- `DELETE /api/certidoes/consultas/{id}` used to hard-delete: blobs first,
-- then the `certidao_consultas` row (CASCADE takes `certidao_resultados`
-- with it). In prod a manual consulta of 12 results + blobs was removed this
-- way and nobody could tell WHO did it or WHEN — the row was simply gone.
-- The owner wants a history of every action; this slice is the first step:
-- a delete becomes RECOVERABLE and ATTRIBUTABLE instead of instant and
-- silent. The full audit trail (every action, not only deletes) is a
-- parallel slice's seed middleware — see `app/modules/certidoes/routers/
-- certidoes.py::excluir_consulta`'s structured log line for the bridge.
--
-- `excluida_em` / `excluida_por` on BOTH tables, not just the consulta:
-- `certidao_resultados` has no FK-cascade equivalent for an UPDATE (CASCADE
-- only fires on DELETE), so the resultado rows are stamped explicitly,
-- in lockstep with their parent, by the same request. Every reader that
-- lists/gets a consulta or a resultado must add `.is_("excluida_em",
-- "null")` — see the return note for the full grep of readers this touched.
--
-- WHY excluida_em/excluida_por AND NOT deleted_at (057/135's column name)
-- ---------------------------------------------------------------------------
-- `deleted_at` is this schema's OTHER soft-delete convention
-- (`cliente_documentos`, `matricula_extracoes`), and it names WHEN but never
-- WHO — those two surfaces don't have an attribution requirement. This one
-- does (that is the entire point of the slice — "nobody can tell who did
-- it"), so the column pair names both, and `excluida_em`/`excluida_por`
-- keeps the Portuguese-verb convention `situacao_origem`/`resultado_origem`
-- (migration 107/116) already use in this same module rather than mixing
-- an English column into an otherwise PT-BR schema.
--
-- RESTORE, NOT UN-DELETE-BY-NULLING-BLINDLY: `POST .../consultas/{id}/
-- restaurar` clears `excluida_em`/`excluida_por` on the consulta AND every
-- one of its resultados — the exact inverse of the soft-delete write, same
-- authz (`get_current_user_org`, org-scoped). Blobs were never touched by
-- the soft-delete, so a restore needs no storage work at all.
--
-- PURGE (30 DAYS): the blobs + rows survive the soft-delete precisely so a
-- mistaken delete is recoverable — but "recoverable forever" is an LGPD
-- retention problem the ORIGINAL hard-delete never had (it removed
-- everything immediately). `app/modules/certidoes/scheduler.py`'s new
-- `certidoes_purge_excluidas` job hard-deletes blobs then rows for anything
-- past `excluida_em + 30 days`, mirroring `meta_ads/services/
-- leadgen_webhook_service.py::purge_processed`'s cutoff-delete shape
-- (`LGPD retention: drop processed inbox rows past the window`).
--
-- FORWARD-ONLY, IDEMPOTENT: `ADD COLUMN IF NOT EXISTS` + `CREATE INDEX IF
-- NOT EXISTS`, no DROP / DELETE / TRUNCATE. Re-running it a second time
-- changes nothing.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the
-- row counts this will touch and the user has given an explicit go-ahead.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. certidao_consultas — soft-delete columns
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.certidao_consultas
    ADD COLUMN IF NOT EXISTS excluida_em  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS excluida_por UUID;

-- The hot read every list/get endpoint runs: "this org's non-deleted
-- consultas, newest first" — narrower than (and preferred over)
-- `idx_sw_certidao_consultas_org_created` (091) for that shape once most
-- consultas are non-deleted, since Postgres can skip every excluded row
-- entirely rather than filtering them out after the index scan.
CREATE INDEX IF NOT EXISTS idx_sw_certidao_consultas_ativas
    ON social_wiring.certidao_consultas (org_id, created_at DESC)
    WHERE excluida_em IS NULL;

-- The purge sweep's read path: every soft-deleted consulta, oldest first —
-- mirrors 057's `idx_sw_cliente_documentos_retencao` shape for the same
-- reason (a cutoff-scan index, not a lookup one).
CREATE INDEX IF NOT EXISTS idx_sw_certidao_consultas_excluidas
    ON social_wiring.certidao_consultas (excluida_em)
    WHERE excluida_em IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 2. certidao_resultados — soft-delete columns
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS excluida_em  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS excluida_por UUID;

-- `certidoes_por_parte`/`certidoes_por_cliente` (service.py's
-- `_resultados_das_consultas`) read resultados by `consulta_id IN (...)`
-- filtered to non-deleted — this is that read path's shape.
CREATE INDEX IF NOT EXISTS idx_sw_certidao_resultados_ativos
    ON social_wiring.certidao_resultados (consulta_id)
    WHERE excluida_em IS NULL;
