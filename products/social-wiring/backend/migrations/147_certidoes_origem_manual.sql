-- ============================================================================
-- Migration 147 · social_wiring: Certidões — registro manual sem InfoSimples
--
-- WHAT
-- ----
-- `POST /api/certidoes/consultas/manual` (`app/modules/certidoes/routers/
-- certidoes.py::criar_consulta_manual`) creates a consulta the SAME shape as
-- the automated `POST /consultas` path — one placeholder resultado per every
-- type the office checklist names (`CERTIDOES_CONFIG` + `MANUAL_TIPOS_CONFIG`,
-- 13 rows) — but never calls InfoSimples and never requires its token. It
-- exists for two real office needs migration 091's automated-only path had no
-- answer for: testing the pipeline/contract with a fictional person WITHOUT
-- sending a fake CPF to a government lookup system, and recording a
-- certidão the office already holds a PDF for (obtained elsewhere, or issued
-- before this product existed) without paying InfoSimples again for it.
--
-- WHY A COLUMN, NOT A DERIVED FACT
-- ---------------------------------------------------------------------------
-- "Was InfoSimples ever billed for this consulta" is NOT reliably derivable
-- from `certidao_resultados.status`/`api_requested_at` after the fact: a
-- manual consulta's resultados stay `status='pendente'` forever (nothing ever
-- advances them — `service.processar_consulta` is never invoked for one), and
-- an AUTOMATED consulta whose every certidão happened to fail before its
-- first successful call would show the same all-`pendente` shape. Only the
-- CONSULTA itself, at creation time, knows which path made it — see
-- `criar_consulta_manual`'s own docstring for the enforcement side (no
-- `background_tasks.add_task(svc.processar_consulta, ...)`, no
-- `svc.check_required_credentials` call, so `cost_ledger.book_infosimples_
-- cost` — reachable only from inside `_process_single_certidao` — can never
-- fire for a manual consulta by construction).
--
-- WHY NOT NULL DEFAULT 'automatica'
-- ---------------------------------------------------------------------------
-- Every consulta created before this migration went through the ONLY path
-- that existed — the automated one. A NULL default here would read as "we
-- don't know", which is false; 'automatica' is the honest backfill for every
-- existing row, the same reasoning `104_visita_proposta.sql`'s own
-- NOT-NULL-with-default column additions use.
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the
-- row counts this will touch and the user has given an explicit go-ahead.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

ALTER TABLE social_wiring.certidao_consultas
    ADD COLUMN IF NOT EXISTS origem TEXT NOT NULL DEFAULT 'automatica';

COMMENT ON COLUMN social_wiring.certidao_consultas.origem IS
    'automatica | manual — automatica: created via POST /consultas, calls '
    'InfoSimples and is billable (cost_ledger). manual: created via '
    'POST /consultas/manual, never calls InfoSimples, never billed — every '
    'resultado is a pendente placeholder a human fills by hand through the '
    'existing PATCH /resultados/{id} confirm/correct flow. See '
    'app/modules/certidoes/routers/certidoes.py::criar_consulta_manual.';

ALTER TABLE social_wiring.certidao_consultas
    DROP CONSTRAINT IF EXISTS certidao_consultas_origem_check;
ALTER TABLE social_wiring.certidao_consultas
    ADD CONSTRAINT certidao_consultas_origem_check
    CHECK (origem IN ('automatica', 'manual'));
