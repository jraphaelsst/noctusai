-- ============================================================================
-- Migration 041 -- erp.processos_venda: the post-proposal execution pipeline
--
-- WHY THIS EXISTS
-- ---------------
-- Roadmap P2.1 (`project-history/roadmaps/erp-processos-venda-2026-07.md`).
-- Accepting a proposal ends the NEGOTIATION and starts EXECUTION. The Funil
-- board answers "will this close?"; this board answers "how far along is the
-- closing?". They are different questions with different stages, so they are
-- different tables -- not one table with a longer enum.
--
-- The seam is a button on the Funil card WHILE IT SITS IN THE `proposta`
-- COLUMN (user correction, roadmap decision log 2026-07-16 -- `fechado` is a
-- Funil-INTERNAL terminal state, not the trigger). On acceptance the deal
-- LEAVES the Funil entirely (negociação status → 'aceita') and appears here.
--
-- PREREQUISITE: migration 040 (erp.negociacoes_venda + erp.agency_profile_id).
--
-- IDEMPOTENT: IF NOT EXISTS / ON CONFLICT DO NOTHING / DROP POLICY IF EXISTS.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. The 8 execution stages -- fixed, from the user's own steps
-- ----------------------------------------------------------------------------
-- Deliberately a FIXED enum, not a configurable workflow: user-configurable
-- stages is a separate product decision and building the abstraction on spec
-- is an explicit roadmap anti-goal.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typname = 'etapa_processo' AND n.nspname = 'erp'
  ) THEN
    CREATE TYPE erp.etapa_processo AS ENUM (
      'elaboracao_contrato',
      'analise_partes',
      'revisao_contrato',
      'assinatura',
      'financiamento_escritura',
      'finalizacao',
      'entrega_chaves',
      'nota_fiscal'
    );
  END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- 2. erp.processos_venda
-- ----------------------------------------------------------------------------
-- `negociacao_venda_id` is UNIQUE, and that is load-bearing: it is the
-- IDEMPOTENCY GUARANTEE for the accept-proposal seam. A double-clicked
-- "Aceitar Proposta" is a real user behaviour, and a check-then-insert in the
-- router would race under concurrent requests. The constraint makes the second
-- insert impossible at the DB rather than merely unlikely in the application.
--
-- `cliente_id` is carried alongside (denormalized through the negociação) per
-- the user's decision that a processo references BOTH. It lets the board read
-- and filter by cliente without a second hop, and it is FK-enforced so it
-- cannot drift from a real cliente.
--
-- `arquivado` resolves roadmap Q3: `nota_fiscal` is TERMINAL (there is no
-- stage after issuing the invoice), so without an archive flag the last column
-- grows without bound and the board becomes unusable within a year. Mirrors
-- `erp.clientes.arquivado` rather than inventing a second vocabulary.
CREATE TABLE IF NOT EXISTS erp.processos_venda (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cliente_id UUID NOT NULL REFERENCES erp.clientes(id) ON DELETE CASCADE,
  negociacao_venda_id UUID NOT NULL UNIQUE
    REFERENCES erp.negociacoes_venda(id) ON DELETE CASCADE,
  corretor_id UUID NOT NULL REFERENCES erp.profiles(id)
    DEFAULT erp.agency_profile_id(),
  etapa erp.etapa_processo NOT NULL DEFAULT 'elaboracao_contrato',
  valor NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (valor >= 0),
  observacoes TEXT,
  kanban_pos INTEGER NOT NULL DEFAULT 0,
  arquivado BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_processos_venda_board
  ON erp.processos_venda (etapa, kanban_pos)
  WHERE arquivado = false;
CREATE INDEX IF NOT EXISTS idx_processos_venda_cliente
  ON erp.processos_venda (cliente_id);
CREATE INDEX IF NOT EXISTS idx_processos_venda_corretor
  ON erp.processos_venda (corretor_id);

DROP TRIGGER IF EXISTS set_timestamps_sp_trigger ON erp.processos_venda;
CREATE TRIGGER set_timestamps_sp_trigger
  BEFORE INSERT OR UPDATE ON erp.processos_venda
  FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();

ALTER TABLE erp.processos_venda ENABLE ROW LEVEL SECURITY;

-- Same shape as erp.clientes / erp.negociacoes_venda (admin OR owning
-- corretor). A processo must never be visible to someone who cannot see the
-- deal it came from.
DROP POLICY IF EXISTS "processos_venda_select" ON erp.processos_venda;
CREATE POLICY "processos_venda_select" ON erp.processos_venda
  FOR SELECT TO authenticated
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = corretor_id
  );

DROP POLICY IF EXISTS "processos_venda_insert" ON erp.processos_venda;
CREATE POLICY "processos_venda_insert" ON erp.processos_venda
  FOR INSERT TO authenticated
  WITH CHECK (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = corretor_id
    OR corretor_id = erp.agency_profile_id()
  );

DROP POLICY IF EXISTS "processos_venda_update" ON erp.processos_venda;
CREATE POLICY "processos_venda_update" ON erp.processos_venda
  FOR UPDATE TO authenticated
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = corretor_id
  );

DROP POLICY IF EXISTS "processos_venda_delete" ON erp.processos_venda;
CREATE POLICY "processos_venda_delete" ON erp.processos_venda
  FOR DELETE TO authenticated
  USING (
    public.has_role((SELECT auth.uid()), 'admin'::erp.app_role)
    OR (SELECT auth.uid()) = corretor_id
  );

DROP POLICY IF EXISTS "service_role_bypass" ON erp.processos_venda;
CREATE POLICY "service_role_bypass" ON erp.processos_venda
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- 3. Page registration
-- ----------------------------------------------------------------------------
-- WITHOUT THIS ROW THE NAV ITEM SILENTLY NEVER RENDERS. `status_pagina` gates
-- every sidebar entry; a page whose row is missing is not "hidden pending
-- launch", it is invisible with no error anywhere. `nome_pagina` must match
-- the `route:` key in `frontend/src/App.tsx` NAV_GROUPS exactly.
INSERT INTO erp.status_pagina (nome_pagina, status, tipo_pagina, descricao)
VALUES (
  'processos-venda',
  'producao',
  'geral',
  'Processos de Venda — execução pós-aceite da proposta'
)
ON CONFLICT (nome_pagina) DO NOTHING;
