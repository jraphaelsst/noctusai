-- ============================================================================
-- Migration 119 · social_wiring: rg/cpf upload — LGPD intake closed, activate
--
-- Migration 057 seeded `cliente_documento_tipos.rg` and `.cpf` with
-- `ativo = false` — a DELIBERATE withhold, not a bug: the upload endpoint
-- (`documentos_service._require_tipo_documento`) refuses any `tipo_documento`
-- that is not `ativo`, so no RG/CPF could be uploaded to a card at all,
-- pending the data-category intake that migration's header named as the
-- gate. That intake is now filed — see `noctus.dev.lgpd_flag` (this change)
-- and `KNOWLEDGE-BASE/CONTEXT/PATTERNS/security/lgpd.md` §11 for the register
-- entry (data category, purpose, retention, legal basis). The user made the
-- activation call 2026-09-16.
--
-- WHAT THIS FILE DOES AND DOES NOT DO
-- -------------------------------------
-- ONE UPDATE, no schema change: `ativo = true` for `rg` and `cpf`. Every
-- other column on those two rows — `categoria_lgpd = 'identidade'`,
-- `retencao_dias = 1825` (same window every other card document carries),
-- `identidade = true` — was already correct in 057 and needs no change here.
-- `descricao` is refreshed off its "retenção pendente" wording, which would
-- otherwise keep reading as still-withheld after this ships.
--
-- IDENTITY EXTRACTION NEEDS NO WIRING — IT WAS ALREADY THERE
-- ---------------------------------------------------------------
-- `identidade_extracao_service.TIPOS_EXTRAIVEIS` already lists `rg`/`cpf`
-- (that module predates this activation and was written against the day
-- these types would be enabled), and `documentos_service.upload_documento`
-- already stamps `extracao_status = 'pendente'` for any type
-- `identidade_svc.deve_extrair()` accepts. `_require_tipo_documento`'s
-- `ativo` check was the ONLY thing stopping an RG/CPF upload from reaching
-- that pipeline — flipping this flag is the entire fix; see
-- `tests/test_migration_119_cliente_identidade_ativacao.py`.
--
-- FORWARD-ONLY, IDEMPOTENT. No DROP / DELETE / TRUNCATE. The UPDATE is
-- naturally idempotent — re-running it a second time changes nothing.
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the
-- row counts this will touch and the user has given an explicit go-ahead.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

UPDATE social_wiring.cliente_documento_tipos
SET
    ativo = true,
    descricao = CASE tipo_documento
        WHEN 'rg' THEN 'RG -- qualificação civil (intake LGPD concluído 2026-09-16)'
        WHEN 'cpf' THEN 'CPF -- qualificação civil (intake LGPD concluído 2026-09-16)'
        ELSE descricao
    END
WHERE tipo_documento IN ('rg', 'cpf');
