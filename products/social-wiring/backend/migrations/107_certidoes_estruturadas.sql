-- ============================================================================
-- Migration 107 · social_wiring: Certidões estruturadas — per-parte, per-field
--
-- WHAT THIS IS FOR
-- ----------------
-- The contract-automation slice ("Promessa de Venda e Compra") needs to ask
-- one question migration 091 has no column for: "for THIS party to THIS
-- deal, is their certidão negativa, positiva, or positiva com efeito de
-- negativa — and since when, and until when?" Today a resultado carries only
-- a free-text `analise_ia` and the raw `api_response` JSONB; a clause
-- generator cannot read either without re-implementing the same parsing
-- logic the backend already has to do to CONFIRM the value.
--
-- 🔴 WHY THIS IS THREE THINGS AT ONCE (fields + linkage + confirmation)
-- -----------------------------------------------------------------------
-- They look separable and are not, because the reason any of them exists is
-- the same one: a certidão feeds a signed legal instrument, so every
-- structured field it contributes needs a stated PROVENANCE (api | ia |
-- manual) and, once a human has looked at it, a LOCK that the automated
-- pipeline (`service._derive_estrutura`) will never silently override — see
-- that function's own docstring for the enforcement side. Linkage
-- (`atendimento_parte_id`) is what makes "per parte" answerable at all: a
-- consulta today knows only a name/CPF, not which side of which deal it is
-- for. Splitting these into three migrations would leave two of them
-- pointing at a column that does not exist yet.
--
-- WHY `cliente_id` NULLABLE, NOT A NEW NOT-NULL REQUIREMENT
-- ------------------------------------------------------------
-- Every consulta issued before this migration — and every one a user creates
-- outside the contract-automation flow (a corretor doing ad-hoc due
-- diligence on a lead, unrelated to any atendimento) — has neither a
-- `cliente_id` nor an `atendimento_parte_id`. A NOT NULL requirement here
-- would either need a backfill that invents a party for rows that never had
-- one, or refuse every future ad-hoc consulta. Both are wrong; this is
-- explicitly an OPTIONAL linkage, set by `POST /consultas/{id}/vincular-parte`
-- once a consulta is attached to a deal, per `app/modules/certidoes/routers/
-- certidoes.py`.
--
-- WHY `resultado` AND `resultado_origem` ARE BOTH NULLABLE
-- -------------------------------------------------------------------------
-- Most resultados, at the moment they turn `status='sucesso'`, do NOT yet
-- have a confident `resultado` — see `registry._parse_resultado_padrao`'s own
-- docstring for why a `code=200` API response is not, by itself, enough to
-- tell a negativa PDF from a positiva one. `resultado IS NULL` therefore
-- means "not yet determined", the same honest silence `imovel_dados.
-- situacao_onus` (migration 099) uses for the same reason: a guessed value
-- here is a WORSE due-diligence artifact than an admittedly-missing one.
--
-- WHY THE CONFIRMATION STAMP IS SEPARATE FROM `resultado_origem`
-- -------------------------------------------------------------------------
-- `resultado_origem='manual'` already tells you a human set the value. It
-- does NOT tell you WHICH human, or WHEN — and a due-diligence dispute asks
-- exactly that question months later, the same reason `atendimento_
-- contratos.status_por`/`status_em` (migration 106) exist beside `status`
-- itself. `confirmado_por`/`confirmado_em` answer it independently of how the
-- value got there, including the "I reviewed the AI's read of the API and it
-- is correct" case, where `resultado_origem` still moves to `manual` (a human
-- now owns this field) but the VALUE itself did not change.
--
-- FORWARD-ONLY, IDEMPOTENT (every step existence-guarded; safe to re-run).
-- 🔴 MIGRATION FILE ONLY — not applied to any database by this change. Apply
-- via `noctus.dev.migrate_product` only after the tech-lead has stated the
-- row counts this will touch and the user has given an explicit go-ahead.
-- See `migrations/APPLIED.md`.
-- ============================================================================

SET search_path = social_wiring, public;

-- ----------------------------------------------------------------------------
-- 1. certidao_resultados — the structured fields
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.certidao_resultados
    ADD COLUMN IF NOT EXISTS numero             TEXT,
    ADD COLUMN IF NOT EXISTS emitida_em         DATE,
    ADD COLUMN IF NOT EXISTS validade_ate       DATE,
    ADD COLUMN IF NOT EXISTS resultado          TEXT,
    ADD COLUMN IF NOT EXISTS resultado_origem   TEXT,
    -- Who confirmed the value shown above, and when. Independent of
    -- `resultado_origem` — see this file's header.
    ADD COLUMN IF NOT EXISTS confirmado_por     UUID,
    ADD COLUMN IF NOT EXISTS confirmado_em      TIMESTAMPTZ;

COMMENT ON COLUMN social_wiring.certidao_resultados.numero IS
    'The certidão''s own control/registration number, read off the API '
    'response, an uploaded PDF (AI-extracted), or typed by a human.';
COMMENT ON COLUMN social_wiring.certidao_resultados.emitida_em IS
    'Emission date PRINTED ON the certidão — not this row''s created_at.';
COMMENT ON COLUMN social_wiring.certidao_resultados.validade_ate IS
    'Validity deadline printed on the certidão, when it states one.';
COMMENT ON COLUMN social_wiring.certidao_resultados.resultado IS
    'negativa | positiva | positiva_com_efeito_de_negativa | nao_emitida. '
    'NULL means not yet determined — see this file''s header for why that is '
    'the honest default rather than a guess. CHECK constraint below is the '
    'vocabulary; kept in sync with app/modules/certidoes/schemas.py''s '
    'ResultadoPatch Literal and registry.RESULTADO_VALUES.';
COMMENT ON COLUMN social_wiring.certidao_resultados.resultado_origem IS
    'api | ia | manual — who last wrote the structured fields above. NULL '
    'alongside a NULL resultado means neither has run yet. See '
    'service._derive_estrutura for the write-side rule this backs: only a '
    'row NOT already ''manual'' (and with no confirmado_por) may be '
    'overwritten by the automated pipeline.';
COMMENT ON COLUMN social_wiring.certidao_resultados.confirmado_por IS
    'Who confirmed/corrected this resultado''s structured fields via '
    'PATCH /api/certidoes/resultados/{id} — set even when the PATCH body '
    'was empty (a pure "I reviewed this and it is correct").';
COMMENT ON COLUMN social_wiring.certidao_resultados.confirmado_em IS
    'When confirmado_por confirmed it.';

ALTER TABLE social_wiring.certidao_resultados
    DROP CONSTRAINT IF EXISTS certidao_resultados_resultado_check;
ALTER TABLE social_wiring.certidao_resultados
    ADD CONSTRAINT certidao_resultados_resultado_check
    CHECK (resultado IS NULL OR resultado IN (
        'negativa', 'positiva', 'positiva_com_efeito_de_negativa', 'nao_emitida'
    ));

ALTER TABLE social_wiring.certidao_resultados
    DROP CONSTRAINT IF EXISTS certidao_resultados_resultado_origem_check;
ALTER TABLE social_wiring.certidao_resultados
    ADD CONSTRAINT certidao_resultados_resultado_origem_check
    CHECK (resultado_origem IS NULL OR resultado_origem IN ('api', 'ia', 'manual'));

-- Supports `vincular_parte`'s idempotent fan-out check ("does this consulta
-- already carry a resultado of tipo X?") and the future staleness sweep the
-- 099 header names as the same kind of not-yet-decided rule.
CREATE INDEX IF NOT EXISTS idx_sw_certidao_resultados_consulta_tipo
    ON social_wiring.certidao_resultados (consulta_id, tipo);

-- ----------------------------------------------------------------------------
-- 2. certidao_consultas — nullable linkage to a party of an atendimento
-- ----------------------------------------------------------------------------
ALTER TABLE social_wiring.certidao_consultas
    ADD COLUMN IF NOT EXISTS cliente_id            UUID,
    ADD COLUMN IF NOT EXISTS atendimento_parte_id   UUID;

COMMENT ON COLUMN social_wiring.certidao_consultas.cliente_id IS
    'The clientes row this consulta is FOR, when it is attached to a deal. '
    'Denormalized off atendimento_parte_id (set together by vincular_parte) '
    'so a caller that only has the person can filter without a join through '
    'atendimento_partes. NULL for ad-hoc consultas not tied to any deal.';
COMMENT ON COLUMN social_wiring.certidao_consultas.atendimento_parte_id IS
    'Which party of which atendimento this consulta''s due diligence is for '
    '(the titular is atendimentos.lead_id itself — see migration 073''s '
    'header — so this only ever names an ADDITIONAL party, exactly as 073 '
    'scopes atendimento_partes). NULL for ad-hoc / pre-107 consultas.';

ALTER TABLE social_wiring.certidao_consultas
    DROP CONSTRAINT IF EXISTS certidao_consultas_cliente_fk;
ALTER TABLE social_wiring.certidao_consultas
    ADD CONSTRAINT certidao_consultas_cliente_fk
    FOREIGN KEY (cliente_id)
    REFERENCES social_wiring.clientes (id) ON DELETE SET NULL;

ALTER TABLE social_wiring.certidao_consultas
    DROP CONSTRAINT IF EXISTS certidao_consultas_atendimento_parte_fk;
ALTER TABLE social_wiring.certidao_consultas
    ADD CONSTRAINT certidao_consultas_atendimento_parte_fk
    FOREIGN KEY (atendimento_parte_id)
    REFERENCES social_wiring.atendimento_partes (id) ON DELETE SET NULL;

-- "Every certidão consulta for this party" — the read `GET /api/certidoes/
-- partes/{atendimento_parte_id}/resultados` runs, per this file's header.
CREATE INDEX IF NOT EXISTS idx_sw_certidao_consultas_atendimento_parte
    ON social_wiring.certidao_consultas (org_id, atendimento_parte_id)
    WHERE atendimento_parte_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sw_certidao_consultas_cliente
    ON social_wiring.certidao_consultas (org_id, cliente_id)
    WHERE cliente_id IS NOT NULL;

-- ----------------------------------------------------------------------------
-- 3. certidao_resultado_acessos — LGPD content-read log
-- ----------------------------------------------------------------------------
-- 🔴 Mirrors `atendimento_documento_acessos` (078) / `atendimento_contrato_
-- versao_acessos` (106) exactly, for the same reason: a certidão is
-- personal data about a natural person (CPF, filiação, débitos), and "who
-- opened this file, and when" has to be answerable. NOT built on
-- `app.services.documento_store.DocumentoStore` directly — that class
-- INSERTS a new document row per upload; a certidão's file lives on the
-- SAME `certidao_resultados` row `criar_consulta`'s fan-out already created
-- (`arquivo_url`, not a `documento_store`-shaped `storage_path`), so only
-- the access-log HALF of that contract applies here. See
-- `service.mint_resultado_url` / `service._log_resultado_acesso`.
CREATE TABLE IF NOT EXISTS social_wiring.certidao_resultado_acessos (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID NOT NULL,
    documento_id UUID NOT NULL
        REFERENCES social_wiring.certidao_resultados (id) ON DELETE CASCADE,
    usuario_id   UUID,
    acao         TEXT NOT NULL CHECK (acao IN ('view', 'download', 'delete')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sw_certidao_resultado_acessos_doc
    ON social_wiring.certidao_resultado_acessos (documento_id, created_at DESC);

ALTER TABLE social_wiring.certidao_resultado_acessos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "certidao_resultado_acessos_select_own_org"
    ON social_wiring.certidao_resultado_acessos;
CREATE POLICY "certidao_resultado_acessos_select_own_org"
    ON social_wiring.certidao_resultado_acessos
    FOR SELECT TO authenticated
    USING (org_id = public.current_org_id());

DROP POLICY IF EXISTS "certidao_resultado_acessos_service_role"
    ON social_wiring.certidao_resultado_acessos;
CREATE POLICY "certidao_resultado_acessos_service_role"
    ON social_wiring.certidao_resultado_acessos
    FOR ALL TO service_role USING (true) WITH CHECK (true);
