-- ============================================================================
-- Migration 160 · social_wiring: `cliente_documento_tipos.descricao` stops
-- carrying the intake-tracking NOTE, keeps only the LABEL
--
-- `GET /api/clientes/documentos/tipos` (`app/modules/card_hub/
-- documentos_service.list_tipos_documento` → the seed's `noctusai_lib.
-- domain.card_hub.documentos.list_tipos_documento`) returns `descricao`
-- VERBATIM as the upload picker's option label. Migration 119 activated
-- `rg`/`cpf` for upload and, in the SAME UPDATE, rewrote `descricao` to:
--     'RG -- qualificação civil (intake LGPD concluído 2026-09-16)'
--     'CPF -- qualificação civil (intake LGPD concluído 2026-09-16)'
-- The compliance note that belongs in 119's own migration header (and does
-- live there — see its header, and `KNOWLEDGE-BASE/CONTEXT/PATTERNS/
-- security/lgpd.md` §11) also ended up on the user-facing label, so every
-- operator opening the upload picker reads an internal audit sentence
-- instead of a plain document name.
--
-- 🔴 THIS IS NOT A REGRESSION 119 INTRODUCED FROM A CLEAN BASELINE — 057's
-- OWN SEED HAD THE SAME SHAPE ONE STEP EARLIER
-- ---------------------------------------------------------------------------
-- 057 seeded these two rows with `'RG -- retenção pendente de intake
-- LGPD'` / `'CPF -- retenção pendente de intake LGPD'` — a process-status
-- note, not a label, from day one. This migration is the first time the
-- column carries neither: every other row in the catalogue already reads as
-- a plain label (057's `'Contratos e aditivos'`, 142's `'CNH — Carteira
-- Nacional de Habilitação (qualificação civil)'`, ...) and `rg`/`cpf` now
-- match that shape.
--
-- FIX AT THE SOURCE, NOT IN THE ROUTER: the seed's `list_tipos_documento`
-- already returns `descricao` as-is — it is not the router or the seed
-- function that conflated label and note, it is this ROW'S DATA. So the fix
-- is a data flip here, not a string-strip layered on top of the read path.
-- The intake date/decision stays exactly where 119's own header already
-- recorded it (migration history + the LGPD register), which is the
-- durable, non-user-facing home for a compliance timestamp — it does not
-- need a second, API-visible home on the picker label.
--
-- FORWARD-ONLY, IDEMPOTENT: a plain UPDATE, no schema change, no DROP /
-- DELETE / TRUNCATE. Re-running it a second time changes nothing.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the
-- row counts this will touch and the user has given an explicit go-ahead.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

UPDATE social_wiring.cliente_documento_tipos
SET descricao = CASE tipo_documento
    WHEN 'rg' THEN 'RG (documento de identidade)'
    WHEN 'cpf' THEN 'CPF (documento de identidade)'
    ELSE descricao
END
WHERE tipo_documento IN ('rg', 'cpf');
