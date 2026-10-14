-- 266 -- imovel_transacoes (ground-truth closing prices, one row per closed sale).
--
-- WHY: the price evaluator's scarcest input is the REAL closing price. SW holds
-- only a handful of atendimento_negociacao.valor_negociado; Vista exposes none.
-- The owner approved reading the price from the signed contracts in the private
-- Drive mirror (noctus.dev.drive_census action=transacoes). This table is where
-- both sources land, so the evaluator reads ONE place.
--
-- PII: none by construction. Price, date, deal number, payment-shape flags and
-- the candidate imóvel codes (with score + evidence NAMES). Never a name, CPF,
-- RG, e-mail, matrícula or address -- those stay in the private dir.
--
-- LINK: a signed contract is matched to a SW imóvel by the importer, which only
-- PROPOSES candidates (vinculo_candidatos). `codigo_canonical` stays NULL and
-- vinculo_status 'pendente' until an org admin confirms (owner rule: every
-- match is confirmed by a human). 'confirmado' therefore REQUIRES a code (CHECK).
-- No FK to imovel_registry on purpose: the service validates the code, and a
-- registry cleanup must never null a confirmed link out from under the CHECK.
--
-- BACKFILL: the SW-native deals are inserted here (idempotent INSERT ... ON
-- CONFLICT DO NOTHING on the unique key, fonte_ref = atendimento id) rather than
-- by a service function: the source is entirely in this database, the set is
-- tiny and closed, and a migration is the only place guaranteed to run exactly
-- where the table is created. Those rows carry their code from SW, so they are
-- born 'confirmado'; a deal with no imovel_codigo stays 'pendente'.
--
-- Forward-only + idempotent. PREREQUISITES: 063, 077, 081 (atendimentos), 214;
-- core 070, 072.

SET search_path = social_wiring, public;

DO $guard$
BEGIN
  IF to_regprocedure('public.current_org_id_for(text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.current_org_id_for(text) (core migration 070) -- apply core first';
  END IF;
  IF to_regprocedure('public.attach_acting_audit_triggers(text, text)') IS NULL THEN
    RAISE EXCEPTION 'this migration requires public.attach_acting_audit_triggers (core migration 072) -- apply core first';
  END IF;
END
$guard$;

CREATE TABLE IF NOT EXISTS social_wiring.imovel_transacoes (
    id                     UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                 UUID          NOT NULL,

    -- Same key as imovel_registry / imovel_preco_historico. NULL until confirmed.
    codigo_canonical       TEXT,
    -- The deal's public number (e.g. the Drive folder "782"). Not PII.
    processo_numero        TEXT,
    tipo                   TEXT          NOT NULL DEFAULT 'venda',

    valor_transacao        NUMERIC(14, 2) NOT NULL,
    -- Contract signature date (SW deals: the closing date). NULL when unknown.
    data_transacao         DATE,
    -- Last asking price before the sale; filled later from imovel_preco_historico.
    valor_anunciado_ultimo NUMERIC(14, 2),

    -- Payment shape (NULL = unknown, e.g. a SW deal that never recorded it).
    financiamento          BOOLEAN,
    fgts                   BOOLEAN,
    permuta                BOOLEAN,
    n_parcelas             INTEGER,

    fonte                  TEXT          NOT NULL,
    -- Folder id / atendimento id. Never a name.
    fonte_ref              TEXT          NOT NULL,

    vinculo_status         TEXT          NOT NULL DEFAULT 'pendente',
    -- [{codigo, pontos, forca, evidencias:[names]}] -- codes + scores, no PII.
    vinculo_candidatos     JSONB         NOT NULL DEFAULT '[]'::jsonb,
    confirmado_por         UUID,
    confirmado_em          TIMESTAMPTZ,

    observacoes            TEXT,
    created_at             TIMESTAMPTZ   NOT NULL DEFAULT now(),

    CONSTRAINT imovel_transacoes_tipo_valido CHECK (tipo IN ('venda')),
    CONSTRAINT imovel_transacoes_fonte_valida CHECK (
        fonte IN ('contrato_d4sign', 'contrato_revisao', 'sw_negociacao', 'manual')
    ),
    CONSTRAINT imovel_transacoes_vinculo_valido CHECK (
        vinculo_status IN ('pendente', 'confirmado', 'rejeitado')
    ),
    CONSTRAINT imovel_transacoes_valor_positivo CHECK (valor_transacao > 0),
    CONSTRAINT imovel_transacoes_anunciado_positivo CHECK (
        valor_anunciado_ultimo IS NULL OR valor_anunciado_ultimo > 0
    ),
    CONSTRAINT imovel_transacoes_parcelas_validas CHECK (n_parcelas IS NULL OR n_parcelas >= 0),
    CONSTRAINT imovel_transacoes_confirmado_exige_codigo CHECK (
        vinculo_status <> 'confirmado' OR codigo_canonical IS NOT NULL
    ),
    CONSTRAINT uq_imovel_transacoes_org_fonte_ref UNIQUE (org_id, fonte, fonte_ref)
);

CREATE INDEX IF NOT EXISTS idx_sw_imovel_transacoes_org_status
    ON social_wiring.imovel_transacoes (org_id, vinculo_status);
CREATE INDEX IF NOT EXISTS idx_sw_imovel_transacoes_org_codigo
    ON social_wiring.imovel_transacoes (org_id, codigo_canonical)
    WHERE codigo_canonical IS NOT NULL;

ALTER TABLE social_wiring.imovel_transacoes ENABLE ROW LEVEL SECURITY;

-- Org members READ; writes are service-side only (importer + admin confirm route).
DROP POLICY IF EXISTS "imovel_transacoes_select_own_org" ON social_wiring.imovel_transacoes;
CREATE POLICY "imovel_transacoes_select_own_org"
    ON social_wiring.imovel_transacoes
    FOR SELECT TO authenticated
    USING (org_id = (SELECT public.current_org_id_for('social_wiring')));

DROP POLICY IF EXISTS "imovel_transacoes_service_role" ON social_wiring.imovel_transacoes;
CREATE POLICY "imovel_transacoes_service_role"
    ON social_wiring.imovel_transacoes
    FOR ALL TO service_role USING (true) WITH CHECK (true);

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON social_wiring.imovel_transacoes FROM anon, authenticated;

COMMENT ON TABLE social_wiring.imovel_transacoes IS
    'Ground-truth closing prices (one row per closed sale) from SW deals and '
    'signed contracts. No PII. codigo_canonical is set only after an admin '
    'confirms the proposed link (vinculo_status).';

-- ── Backfill: SW-native won deals ───────────────────────────────────────
INSERT INTO social_wiring.imovel_transacoes (
    org_id, codigo_canonical, tipo, valor_transacao, data_transacao,
    financiamento, fgts, fonte, fonte_ref, vinculo_status, confirmado_em
)
SELECT n.org_id,
       n.imovel_codigo,
       'venda',
       n.valor_negociado,
       (a.closed_at AT TIME ZONE 'America/Sao_Paulo')::date,
       n.financiamento,
       n.fgts,
       'sw_negociacao',
       n.atendimento_id::text,
       CASE WHEN n.imovel_codigo IS NULL THEN 'pendente' ELSE 'confirmado' END,
       CASE WHEN n.imovel_codigo IS NULL THEN NULL ELSE now() END
  FROM social_wiring.atendimento_negociacao n
  JOIN social_wiring.atendimentos a ON a.id = n.atendimento_id
 WHERE a.status = 'aceita'
   AND a.closed_at IS NOT NULL
   AND n.valor_negociado IS NOT NULL
   AND n.valor_negociado > 0
ON CONFLICT (org_id, fonte, fonte_ref) DO NOTHING;

-- Acting-audit trigger for the new table (migration 214, idempotent).
SELECT public.attach_acting_audit_triggers('social_wiring');

NOTIFY pgrst, 'reload schema';
