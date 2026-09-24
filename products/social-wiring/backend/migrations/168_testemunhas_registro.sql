-- ============================================================================
-- Migration 168 · social_wiring: `org_testemunhas` becomes a REGISTRY, and a
-- contract SELECTS which of them sign it
-- ============================================================================
-- WHAT THIS IS FOR
-- ----------------
-- Owner request: a page to register witnesses (nome, celular, email, cpf),
-- and on the card, choose HOW MANY witnesses a contract has and SELECT which
-- registered witnesses those are.
--
-- Migration 108 built `org_testemunhas` as a fixed pair ("the office's two
-- standing witnesses"), enforced by `enforce_max_org_testemunhas_trigger`.
-- That ceiling is gone: an office may register as many witnesses as it
-- likes and pick a different subset per contract. The trigger + its backing
-- function are dropped outright — nothing else references either.
--
-- 🔴 OWNER DECISIONS (confirmed) — CPF replaces RG on the contract
-- -------------------------------------------------------------------------
-- CPF is now REQUIRED (valid mod-11) for every NEW witness, and the
-- contract PRINTS CPF INSTEAD OF RG (RG leaves the registration form
-- entirely — see `TestemunhasSection.tsx`, `derivacao.py`,
-- `modelo_texto.py`). `cpf` stays NULLABLE at the DB level on purpose: the
-- 2 rows already in prod carry RG + e-mail and NO CPF. They are KEPT, shown
-- flagged "CPF pendente", and are simply not selectable for a contract
-- until an operator adds a CPF via PATCH — CPF-required is enforced in the
-- API body (`TestemunhaCreateBody`, `settings_router.py`) for CREATE, and
-- again at SELECTION time (`contrato_testemunhas_service.definir`) and at
-- readiness/send time (`derivacao._imobiliaria`), never by a DB CHECK that
-- would either reject those two rows or need a NOT VALID escape hatch.
-- `rg` is UNCHANGED (still nullable, still there for the two legacy rows) —
-- it is simply no longer collected on the form or printed on a contract.
--
-- WHAT CHANGES
-- ------------
-- 1. `org_testemunhas` gains `celular` (the owner's requested field) and
--    loses its 2-per-org ceiling.
-- 2. `contrato_testemunhas` — new join table, one row per (contrato,
--    testemunha) the operator selected for THAT contract, `ordem`-ranked so
--    the print order is stable and deliberate (never `created_at`, which a
--    re-save would reorder). Keyed to `atendimento_contratos.id` — a
--    contract's witness block is a property of the CONTRACT, not the
--    negociação (an atendimento can carry more than one contract, migration
--    106's own header). `ON DELETE CASCADE` both ways: a deleted contract
--    drops its selection with it, and deleting a registry witness (rare —
--    the settings page does not check usage before deleting) never leaves
--    a dangling FK.
-- 3. A `status_pagina` row for the new "Testemunhas" settings page,
--    same pattern migration 100's own nav-gating footer uses.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. org_testemunhas — drop the 2-per-org cap, add celular
-- ----------------------------------------------------------------------------
DROP TRIGGER IF EXISTS enforce_max_org_testemunhas_trigger
    ON social_wiring.org_testemunhas;
DROP FUNCTION IF EXISTS social_wiring.enforce_max_org_testemunhas();

ALTER TABLE social_wiring.org_testemunhas
    ADD COLUMN IF NOT EXISTS celular TEXT;

COMMENT ON TABLE social_wiring.org_testemunhas IS
    'Per-org REGISTRY of signature witnesses (migration 168 dropped the '
    'migration-108 2-per-org ceiling — reused across contracts, a contract '
    'SELECTS a subset via contrato_testemunhas, never all of them '
    'implicitly). cpf is required for every new row (enforced in the API, '
    'not here) but stays nullable — the 2 rows migration 108 shipped carry '
    'no CPF and are kept, flagged "CPF pendente", not selectable until one '
    'is added.';

COMMENT ON COLUMN social_wiring.org_testemunhas.celular IS
    'Migration 168 — the owner''s requested contact field. Optional, never '
    'printed on a contract, never required for selection (unlike cpf).';

COMMENT ON COLUMN social_wiring.org_testemunhas.cpf IS
    'Required (mod-11) for every witness created after migration 168 — '
    'enforced in TestemunhaCreateBody, not by a DB CHECK, so the 2 rows '
    'migration 108 shipped without one are never invalidated. NULL means '
    '"CPF pendente" — not selectable for a contract (contrato_testemunhas_'
    'service.definir refuses it) and never printed.';

COMMENT ON COLUMN social_wiring.org_testemunhas.rg IS
    'Migration 168: no longer collected on the registration form and no '
    'longer printed on a contract (CPF replaces it there) — kept only for '
    'the 2 legacy rows that still carry one.';

-- ----------------------------------------------------------------------------
-- 2. contrato_testemunhas — per-contract witness selection
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.contrato_testemunhas (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        UUID NOT NULL,
    contrato_id   UUID NOT NULL
        REFERENCES social_wiring.atendimento_contratos (id) ON DELETE CASCADE,
    testemunha_id UUID NOT NULL
        REFERENCES social_wiring.org_testemunhas (id) ON DELETE CASCADE,

    -- Print/selection order — 1-based, deliberate, never inferred from
    -- created_at (a re-save via `definir` always rewrites the whole set).
    ordem         INT NOT NULL DEFAULT 1,

    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_por   UUID,

    -- One selection row per witness per contract — `definir` replaces the
    -- whole set rather than upserting, but the constraint stays as the
    -- backstop (same "checked in the service AND held by the DB" posture
    -- migration 108's own cap took).
    UNIQUE (contrato_id, testemunha_id)
);

COMMENT ON TABLE social_wiring.contrato_testemunhas IS
    'Which of the org''s registered testemunhas (org_testemunhas) sign THIS '
    'contract, and in what order. Written wholesale by '
    'contrato_testemunhas_service.definir (delete-then-insert, never a '
    'partial patch) — see migration 168 header.';

CREATE INDEX IF NOT EXISTS idx_sw_contrato_testemunhas_contrato
    ON social_wiring.contrato_testemunhas (contrato_id, ordem);

CREATE INDEX IF NOT EXISTS idx_sw_contrato_testemunhas_testemunha
    ON social_wiring.contrato_testemunhas (testemunha_id);

ALTER TABLE social_wiring.contrato_testemunhas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "contrato_testemunhas_select_own_org"
    ON social_wiring.contrato_testemunhas;
CREATE POLICY "contrato_testemunhas_select_own_org"
    ON social_wiring.contrato_testemunhas
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "contrato_testemunhas_write_own_org"
    ON social_wiring.contrato_testemunhas;
CREATE POLICY "contrato_testemunhas_write_own_org"
    ON social_wiring.contrato_testemunhas
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id())
    WITH CHECK (org_id = public.current_org_id());

DROP POLICY IF EXISTS "contrato_testemunhas_service_role"
    ON social_wiring.contrato_testemunhas;
CREATE POLICY "contrato_testemunhas_service_role"
    ON social_wiring.contrato_testemunhas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. Nav gating for the new "Testemunhas" settings page
-- ----------------------------------------------------------------------------
INSERT INTO social_wiring.status_pagina (nome_pagina, status)
VALUES ('testemunhas', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
