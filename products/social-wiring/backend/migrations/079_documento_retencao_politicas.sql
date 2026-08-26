-- ============================================================================
-- Migration 079 · social_wiring: one retention policy table, and a UI for it
--
-- Migration 078 shipped `atendimento_documentos.retencao_ate` and left it
-- NULL, deliberately: "a wrong retention clock deletes evidence mid-transaction"
-- and the period was the controller's decision, not an agent's. The owner has
-- now asked for a recommendation AND for the number to stay changeable.
--
-- 🔴 WHY A NEW TABLE AND NOT A COLUMN ON `cliente_documento_tipos`
-- ----------------------------------------------------------------
-- 057 put `retencao_dias` on the TYPE CATALOGUE, which conflates two things
-- that have different owners and different lifetimes:
--
--   * the CATALOGUE — which types exist, which are `ativo`, which are
--     `identidade`, what `categoria_lgpd` they fall under. Platform-owned,
--     changes when we ship code, identical for every tenant.
--   * the POLICY — how long we keep them. CONTROLLER-owned (the agency's
--     call under LGPD art. 15/16), and a thing a human must be able to change
--     from a screen without a migration.
--
-- Leaving retention on the catalogue means the only way to change it is a
-- migration, which is exactly what the owner asked not to have. So policy
-- moves here and the catalogue keeps the catalogue.
--
-- `cliente_documento_tipos.retencao_dias` is NOT dropped — it is the rollback
-- path for one release and gets a COMMENT marking it superseded. The seed
-- below copies its live values across, so the effective retention for every
-- existing cliente type is provably unchanged by this migration (asserted by
-- a test, not by reading).
--
-- 🔴 `org_id IS NULL` = THE PLATFORM DEFAULT, not "no org"
-- --------------------------------------------------------
-- Two tiers, resolved org-row-then-platform-row. The platform row is the
-- code-owned recommendation shipped below; an org row is written the first
-- time a human changes that type on the Settings screen. Deleting the org row
-- restores the default — which is why "restaurar padrão" is a real button and
-- not a re-typed number.
--
-- 🔴 THE CLOCK ANCHOR DIFFERS PER SURFACE, AND THAT IS THE POINT
-- ---------------------------------------------------------------
-- `cliente_documentos` stamps `retencao_ate` at UPLOAD (057, unchanged).
--
-- `atendimento_documentos` must NOT. Lei 9.613/98 art. 10 III — which binds
-- real-estate brokers as obligated persons — sets its minimum "a contar da
-- conclusão da transação", and a deal takes months. Anchoring at upload would
-- expire a document collected in month 1 a full deal-length BEFORE the legal
-- minimum, silently. So the atendimento clock starts at
-- `atendimentos.closed_at` and a document belonging to an OPEN deal has no
-- expiry at all — which is also the honest description of an open deal: the
-- paperwork is still in active use.
--
-- `imovel_documentos` is absent from `superficie` on purpose. 075 gave it no
-- `retencao_ate` column and no access log, because a matrícula is a public
-- registry document about a PROPERTY. Offering a retention control that
-- nothing reads would be a lying UI; when that surface earns a clock, it earns
-- a CHECK value here in the same change.
--
-- FORWARD-ONLY, IDEMPOTENT.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. documento_retencao_politicas
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS social_wiring.documento_retencao_politicas (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- NULL = the platform default. See header.
    org_id         UUID,

    superficie     TEXT NOT NULL
        CHECK (superficie IN ('cliente', 'atendimento')),
    tipo_documento TEXT NOT NULL,

    -- NULL = keep indefinitely, DELIBERATELY. The sweep skips a NULL rather
    -- than treating it as "expire now" — same contract 057 chose, and the
    -- difference between the two readings is every document in the table.
    -- >= 1, not >= 0. Zero would mean "expire the moment the clock starts",
    -- which nobody sets on purpose, and it is falsy — the existing upload path
    -- reads `if retencao_dias`, so a 0 would silently behave as "no clock"
    -- while the screen showed a policy. NULL is already the way to say
    -- "keep indefinitely"; there is no second way.
    retencao_dias  INTEGER
        CHECK (retencao_dias IS NULL OR retencao_dias >= 1),

    -- Why the controller chose this number. Free text, optional, and the
    -- thing an audit actually asks for: art. 6 requires purpose limitation to
    -- be demonstrable, and a bare integer demonstrates nothing.
    motivo         TEXT,

    atualizado_em  TIMESTAMPTZ,
    atualizado_por UUID,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE social_wiring.documento_retencao_politicas IS
    'Controller-owned document retention policy. org_id NULL = platform '
    'default; an org row overrides it. Resolved org-then-platform by '
    'app/services/documento_retencao.py.';

COMMENT ON COLUMN social_wiring.documento_retencao_politicas.retencao_dias IS
    'NULL = keep indefinitely (the sweep skips it), never "expire now".';

-- One policy per (org, superficie, tipo). Two partial uniques because NULL is
-- not equal to NULL in a plain UNIQUE — without the first index, the platform
-- tier could silently acquire duplicate rows and the resolver would pick
-- whichever came back first.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_doc_retencao_platform
    ON social_wiring.documento_retencao_politicas (superficie, tipo_documento)
    WHERE org_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_sw_doc_retencao_org
    ON social_wiring.documento_retencao_politicas (org_id, superficie, tipo_documento)
    WHERE org_id IS NOT NULL;

ALTER TABLE social_wiring.documento_retencao_politicas ENABLE ROW LEVEL SECURITY;

-- Read is open to any authenticated member for their own org AND for the
-- platform tier — a user must be able to see the default they are overriding.
DROP POLICY IF EXISTS "documento_retencao_politicas_select"
    ON social_wiring.documento_retencao_politicas;
CREATE POLICY "documento_retencao_politicas_select"
    ON social_wiring.documento_retencao_politicas
    FOR SELECT TO authenticated
    USING (org_id IS NULL OR org_id = public.current_org_id());

-- 🔴 No authenticated INSERT/UPDATE/DELETE policy. Writes go through the
-- admin-gated endpoint on the service-role client, so the platform tier can
-- never be edited by a tenant even if a token leaks into a direct PostgREST
-- call. The admin check lives in the router; this is the backstop.
DROP POLICY IF EXISTS "documento_retencao_politicas_service_role"
    ON social_wiring.documento_retencao_politicas;
CREATE POLICY "documento_retencao_politicas_service_role"
    ON social_wiring.documento_retencao_politicas
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 2. Platform defaults — cliente surface, COPIED from the live catalogue
-- ----------------------------------------------------------------------------
-- 🔴 Not retyped. Reading the numbers out of `cliente_documento_tipos` is what
-- makes "this migration changes no effective retention" a fact rather than a
-- claim — a typo here would silently re-date every existing document.
INSERT INTO social_wiring.documento_retencao_politicas
    (org_id, superficie, tipo_documento, retencao_dias, motivo)
SELECT
    NULL,
    'cliente',
    t.tipo_documento,
    t.retencao_dias,
    'Migrado de cliente_documento_tipos (057) sem alteração de valor.'
FROM social_wiring.cliente_documento_tipos t
ON CONFLICT DO NOTHING;

COMMENT ON COLUMN social_wiring.cliente_documento_tipos.retencao_dias IS
    'SUPERSEDED by social_wiring.documento_retencao_politicas (079). Kept for '
    'one release as the rollback path; application code MUST NOT read it.';

-- ----------------------------------------------------------------------------
-- 3. Platform defaults — atendimento surface (the recommendation)
-- ----------------------------------------------------------------------------
-- Two clearly different groups, and flattening them to one number would be
-- the easy wrong answer:
--
-- ESCRITURA (10 years / 3650d) — a certidão de casamento and the pacto
-- antenupcial deed+registration evidence the marital property regime, which
-- is precisely what a later challenge to the sale attacks. Claims arising
-- from the contract prescribe in 10 years (CC art. 205). The cartório holds
-- the originals, so our copy expiring is not loss of evidence — but for the
-- decade a claim can be brought, the deal file should be complete.
--
-- COMPROVANTE DE RESIDÊNCIA (5 years / 1825d) — a KYC record, not a title
-- document. Lei 9.613/98 art. 10 III binds real-estate brokers to keep client
-- identification records for a minimum of five years from the conclusion of
-- the transaction. Five years, anchored at closed_at, IS that minimum.
--
-- FGTS SET (2 years / 730d) — 🔴 the shortest on purpose, and the group where
-- a long default would be the actual LGPD failure. An imposto de renda com
-- recibo is a person's entire declared income; a carteira de trabalho is
-- their employment history; extratos are their savings. The purpose they were
-- collected for ENDS when the bank approves or refuses — and the bank keeps
-- its own copies under its own obligation, so we are not the archive of
-- record for any of it. Two years past the deal's close covers a re-
-- application, a fallen-through financing and the closing itself, which is
-- every question we could still be asked. Keeping a buyer's tax return for a
-- decade because it was convenient is the shape art. 15/16 argues against.
INSERT INTO social_wiring.documento_retencao_politicas
    (org_id, superficie, tipo_documento, retencao_dias, motivo)
VALUES
    (NULL, 'atendimento', 'certidao_casamento',          3650,
     'Regime de bens: prescrição decenal de pretensões contratuais (CC art. 205).'),
    (NULL, 'atendimento', 'escritura_pacto',             3650,
     'Regime de bens: prescrição decenal de pretensões contratuais (CC art. 205).'),
    (NULL, 'atendimento', 'registro_pacto',              3650,
     'Regime de bens: prescrição decenal de pretensões contratuais (CC art. 205).'),
    (NULL, 'atendimento', 'comprovante_residencia',      1825,
     'Identificação do cliente: mínimo de 5 anos da conclusão (Lei 9.613/98 art. 10, III).'),
    (NULL, 'atendimento', 'imposto_renda_com_recibo',     730,
     'Renda declarada: finalidade encerra na decisão do banco, que guarda a própria via.'),
    (NULL, 'atendimento', 'carteira_trabalho',            730,
     'Histórico laboral: finalidade encerra na decisão do banco.'),
    (NULL, 'atendimento', 'extratos_fgts',                730,
     'Saldos de FGTS: finalidade encerra na decisão do banco.'),
    (NULL, 'atendimento', 'comprovante_residencia_1ano',  730,
     'Coletado especificamente para a análise do FGTS.')
ON CONFLICT DO NOTHING;
