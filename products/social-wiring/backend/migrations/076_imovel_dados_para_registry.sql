-- ============================================================================
-- Migration 076 · social_wiring: point the imóvel's cartório data at the
-- REGISTRY, not at the Vista mirror. Corrects migration 075.
--
-- 🔴 WHAT 075 GOT WRONG
-- ---------------------
-- 075's own header argues at length that authored data must not live inside a
-- mirror of somebody else's system — and then FK'd both of its tables to
-- `social_wiring.imoveis (org_id, codigo)`, which IS that mirror, with
-- ON DELETE CASCADE. It protected the data from being nulled by a widened
-- sync payload and left it deletable by the disposable table.
--
-- Migration 063 had already settled this in one sentence: "`imoveis` — cache
-- of what Vista says TODAY. Overwritten nightly. Delete it entirely and the
-- next sync rebuilds it. `imovel_registry` — one row per código we have EVER
-- seen. APPEND-ONLY. **Everything of ours joins HERE, never to the mirror.**"
--
-- TWO CONSEQUENCES, ONE OF THEM ALREADY LIVE
-- ------------------------------------------
-- 1. **Reachability — live today, measured on prod 2026-08-25.**
--    `imovel_registry` holds 3017 imóveis; 1062 of them (35%) have
--    `ativo_no_vista = false`, i.e. they have left the Vista catalog and are
--    NOT in the 2008-row mirror. Under 075 those 1009 imóveis could not hold
--    a matrícula at all — the service's existence check 404s them.
--
--    🔴 And they are precisely the wrong ones to lose: an imóvel leaves the
--    catalog when it is SOLD, which is exactly when its matrícula, its guia
--    de IPTU and its registry number are being handled. The feature would
--    have worked for every property except the ones in the middle of the
--    transaction it was built for.
--
-- 2. **Durability — latent.** No code deletes from the mirror today, so
--    nothing has been lost. But 063 calls the mirror disposable and invites
--    exactly that ("delete it entirely and the next sync rebuilds it"). With
--    CASCADE, "rebuild the cache" silently means "destroy the deeds".
--
-- WHY THIS IS SAFE TO RUN
-- -----------------------
-- Both tables are EMPTY (0 rows, prod, 2026-08-25) — 075 landed minutes ago
-- and no product code had written to it yet. Nothing is migrated; only the
-- constraints move.
--
-- Verified before writing this file (prod, 2026-08-25):
--   · every one of the 2008 mirror rows already has a registry row (0 missing),
--     so repointing loses no currently-listed imóvel;
--   · `imovel_registry.codigo_canonical` and `imoveis.codigo` are BOTH already
--     uppercase everywhere (0 exceptions), so the existing `codigo.upper()`
--     the service applies matches the canonical form exactly — no re-keying.
--
-- 🔴 CASCADE IS KEPT, and now means something different: `imovel_registry` is
-- append-only by design, so the cascade is a statement about referential
-- integrity rather than a live deletion path.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. imovel_dados → imovel_registry
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_imovel_fk;

ALTER TABLE social_wiring.imovel_dados
    DROP CONSTRAINT IF EXISTS imovel_dados_registry_fk;
ALTER TABLE social_wiring.imovel_dados
    ADD CONSTRAINT imovel_dados_registry_fk
    FOREIGN KEY (org_id, codigo)
    REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical)
    ON DELETE CASCADE;

COMMENT ON TABLE social_wiring.imovel_dados IS
    'Cartório/registry data WE author for an imóvel. Keyed to '
    '`imovel_registry` (permanent, append-only), NOT to `imoveis` (the '
    'disposable Vista mirror) — see migration 076. An imóvel that has left '
    'the Vista catalog keeps its matrícula, which is the whole point: it '
    'leaves the catalog because it was SOLD.';

-- ----------------------------------------------------------------------------
-- 2. imovel_documentos → imovel_registry
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.imovel_documentos
    DROP CONSTRAINT IF EXISTS imovel_documentos_imovel_fk;

ALTER TABLE social_wiring.imovel_documentos
    DROP CONSTRAINT IF EXISTS imovel_documentos_registry_fk;
ALTER TABLE social_wiring.imovel_documentos
    ADD CONSTRAINT imovel_documentos_registry_fk
    FOREIGN KEY (org_id, codigo)
    REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical)
    ON DELETE CASCADE;

COMMENT ON TABLE social_wiring.imovel_documentos IS
    'Matrícula / guia de IPTU for an imóvel. Keyed to `imovel_registry` — see '
    'migration 076 for why never to the `imoveis` mirror.';
