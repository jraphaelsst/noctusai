-- ============================================================================
-- Migration 144 · social_wiring: backfill `atendimento_negociacao_parcelas.ordem`
-- for every row created before `criar_parcela` computed it server-side
-- ============================================================================
-- WHAT THIS IS FOR
-- ----------------
-- `negociacao_estruturada_service.criar_parcela` (108) wrote
-- `"ordem": valores.get("ordem", 0)` — and `ParcelaCreateBody` never accepted
-- an `ordem` field from the client, so EVERY parcela created through the
-- single-create endpoint landed at `ordem=0`. Only the batch
-- "dividir saldo" path (`dividir_saldo_em_parcelas`) ever computed a real
-- `ordem_base = max(existing) + 1`.
--
-- This matters because `ordem` drives:
--   - the printed "Parcela 01/02/03…" numbering in a generated contract
--     (`contrato_gerador.derivacao.parcelas_ordenadas` sorts by `ordem`);
--   - the `VENCIMENTOS_FORA_DE_ORDEM` readiness blocker;
--   - `posse_marco_parcela_id` / `permuta_posse_marco_parcela_id`, which cite
--     "the parcela that starts the possession clock" by id — a fact that only
--     means something once the parcelas actually HAVE a stable order.
--
-- With every row tied at `ordem=0`, `_listar_parcelas_rows`'s
-- `ORDER BY (ordem, created_at)` tie-break on `created_at` is what has
-- ACTUALLY been determining print order — this backfill makes that order
-- durable in `ordem` itself instead of leaning on insertion order forever.
--
-- WHAT CHANGES
-- ------------
-- Renumbers `ordem` to a dense 0..N-1 sequence PER `atendimento_id`,
-- preserving each atendimento's CURRENT effective order
-- (`ORDER BY ordem, created_at` — the exact tie-break `_listar_parcelas_rows`
-- already uses) so no existing contract's parcela numbering changes; it only
-- stops depending on `created_at` as an accidental fallback. Idempotent: a
-- second run is a no-op (the `WHERE ordem IS DISTINCT FROM` guard skips rows
-- already correct) and safe to re-run after `criar_parcela` starts computing
-- `ordem` correctly for new rows (this migration only touches EXISTING rows).
--
-- FORWARD-ONLY, IDEMPOTENT.
-- 🔴 MIGRATION FILE ONLY — applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

WITH ranked AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY atendimento_id
            ORDER BY ordem, created_at
        ) - 1 AS nova_ordem
    FROM social_wiring.atendimento_negociacao_parcelas
)
UPDATE social_wiring.atendimento_negociacao_parcelas p
SET ordem = ranked.nova_ordem
FROM ranked
WHERE ranked.id = p.id
  AND p.ordem IS DISTINCT FROM ranked.nova_ordem;
