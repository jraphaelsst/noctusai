-- ============================================================================
-- Migration 175 -- social_wiring: automatic divergence resolution for the
-- three `<entidade>_campo_conflitos` tables (cliente/imovel/empresa)
--
-- WHAT THIS IS
-- ------------
-- Owner directive, 2026-09-29, quoted verbatim:
--
--   "Those data divergencies we've been having on extractions, i need you
--   to reason on how to solve this and resolve divergencies without the
--   need of a human. You are to do this using docs and done contracts."
--
-- `app.services.divergencia_resolucao` (code, not this migration) decides
-- validators -> corroboration -> measured source-precision tier -> human,
-- against evidence measured on the 10 signed P2 contracts. When it decides,
-- `campo_conflitos.resolver_e_registrar` needs somewhere to write the
-- verdict AUDITABLE -- this migration adds exactly that, to all three
-- tables the shared `app.services.campo_conflitos` module already treats
-- identically (`ConflictTable.table` — 138/154/167's own N=3
-- formalization, P0c contract §H6). Written as three plain, literal
-- `ALTER TABLE` statements (not a dynamic `FOREACH`/`EXECUTE format()`
-- loop) ON PURPOSE: `noctusai_lib.testing.migration_parser`'s regex-based
-- schema reader cannot resolve a `%I`-parameterized table name (see that
-- module's own "dynamic DDL blind spots" docstring, migration 046's rename
-- loop being the corpus's one example) -- a dynamic loop here would make
-- `motivo_resolucao` invisible to `MockSupabaseClient(validate_schema_
-- constraints=True)` and every test touching it would fail with "table has
-- no column motivo_resolucao" for a column this file plainly adds.
--
-- WHAT CHANGES, PER TABLE
-- ------------------------
-- 1. `status` gains a fourth value: `'resolvido_automatico'` — a divergence
--    the resolver settled on its own, NEVER shown to a human as `pendente`.
--    `decidido_por` stays NULL for it (a SYSTEM resolution, same convention
--    `registrar_conflito`'s own supersede-on-disagreeing-dedupe already
--    uses for its `'rejeitado'` rows), `decidido_em` stamps WHEN.
-- 2. `motivo_resolucao TEXT` -- the rule name + the evidence that decided
--    it (e.g. "[tier] cpf: 'cnh' tem precisão medida 100% (n=19) contra
--    67% (n=3) de 'certidao_casamento'."), NULL for every row a human
--    decided (`'aceito'`/`'rejeitado'`) or that is still `'pendente'` --
--    this column is populated ONLY by the automatic resolver.
--
-- FORWARD-ONLY, IDEMPOTENT (the CHECK drop+recreate is safe to re-run;
-- `ADD COLUMN IF NOT EXISTS` guards the column). Postgres's own default
-- name for an inline, unnamed CHECK on `status` is `<table>_status_check`
-- -- the name every `DROP CONSTRAINT IF EXISTS` below targets.
-- 🔴 MIGRATION FILE ONLY -- applying is the tech-lead's + user's decision.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- 1. cliente_campo_conflitos (migration 138)
ALTER TABLE social_wiring.cliente_campo_conflitos
    DROP CONSTRAINT IF EXISTS cliente_campo_conflitos_status_check;
ALTER TABLE social_wiring.cliente_campo_conflitos
    ADD CONSTRAINT cliente_campo_conflitos_status_check
    CHECK (status IN ('pendente', 'aceito', 'rejeitado', 'resolvido_automatico'));
ALTER TABLE social_wiring.cliente_campo_conflitos
    ADD COLUMN IF NOT EXISTS motivo_resolucao TEXT;
COMMENT ON COLUMN social_wiring.cliente_campo_conflitos.motivo_resolucao IS
    'Populated only when status=''resolvido_automatico'' -- the rule '
    '(validador/rg_prefixo_dv/corroboracao/tier) and the measured evidence '
    'that decided it, from app.services.divergencia_resolucao. Migration 175.';

-- 2. imovel_campo_conflitos (migration 154)
ALTER TABLE social_wiring.imovel_campo_conflitos
    DROP CONSTRAINT IF EXISTS imovel_campo_conflitos_status_check;
ALTER TABLE social_wiring.imovel_campo_conflitos
    ADD CONSTRAINT imovel_campo_conflitos_status_check
    CHECK (status IN ('pendente', 'aceito', 'rejeitado', 'resolvido_automatico'));
ALTER TABLE social_wiring.imovel_campo_conflitos
    ADD COLUMN IF NOT EXISTS motivo_resolucao TEXT;
COMMENT ON COLUMN social_wiring.imovel_campo_conflitos.motivo_resolucao IS
    'Populated only when status=''resolvido_automatico'' -- the rule '
    '(validador/rg_prefixo_dv/corroboracao/tier) and the measured evidence '
    'that decided it, from app.services.divergencia_resolucao. Migration 175.';

-- 3. empresa_campo_conflitos (migration 167)
ALTER TABLE social_wiring.empresa_campo_conflitos
    DROP CONSTRAINT IF EXISTS empresa_campo_conflitos_status_check;
ALTER TABLE social_wiring.empresa_campo_conflitos
    ADD CONSTRAINT empresa_campo_conflitos_status_check
    CHECK (status IN ('pendente', 'aceito', 'rejeitado', 'resolvido_automatico'));
ALTER TABLE social_wiring.empresa_campo_conflitos
    ADD COLUMN IF NOT EXISTS motivo_resolucao TEXT;
COMMENT ON COLUMN social_wiring.empresa_campo_conflitos.motivo_resolucao IS
    'Populated only when status=''resolvido_automatico'' -- the rule '
    '(validador/rg_prefixo_dv/corroboracao/tier) and the measured evidence '
    'that decided it, from app.services.divergencia_resolucao. Migration 175.';
